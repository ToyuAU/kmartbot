"""
Paydock payment tokenisation and 3DS authentication flow.
Ported and cleaned from kmartbot-main/Classes/Bot.py (processPayment / process_paydock_3ds).

Flow:
  1. POST to Paydock to tokenise the raw card → one-time token
  2. POST to Kmart GraphQL create3DSToken → JWT → decode → tokenData
  3. GET 3DS initialization_url (gpayments.net)
  4. POST browser fingerprint form chain
  5. Poll Paydock standalone-3ds/process until success / challenge / failure
"""

import asyncio
import base64
import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from backend.models.card import Card
from backend.services.http_client import HttpClient
from backend.services import discord
from backend.services.discord import notify_challenge
import backend.sites.kmart.graphql as gql

PAYDOCK_PUBLIC_KEY = "5b12b8af610ca9e784c0f86ab5b9657e66fadbc0"
PAYDOCK_TOKEN_URL = "https://api.paydock.com/v1/payment_sources/tokens"
PAYDOCK_3DS_PROCESS_URL = "https://api.paydock.com/v1/charges/standalone-3ds/process"


def _card_payload(card: Card) -> dict:
    return {
        "type": "card",
        "card_name": card.cardholder,
        "card_number": card.number,
        "expire_month": card.expiry_month,
        "expire_year": card.expiry_year,
        "card_ccv": card.cvv,
        "gateway_id": "",
        "store_ccv": True,
        "meta": {},
    }


def _decode_3ds_jwt(token: str) -> dict:
    """Decode the base64url JWT returned by create3DSToken → dict."""
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT format")
    padding = len(parts[1]) % 4
    if padding:
        parts[1] += "=" * (4 - padding)
    decoded = base64.urlsafe_b64decode(parts[1])
    data = json.loads(decoded)
    data["xAccessToken"] = token
    return data


def _extract_form(soup: BeautifulSoup) -> Optional[tuple[str, dict]]:
    """Return (action, fields) from the first form in the soup, or None."""
    form = soup.find("form")
    if not form or not form.get("action"):
        return None
    action = form["action"].replace("&amp;threeDSMethodTimedOut=true", "")
    fields = {}
    for inp in form.find_all("input"):
        if inp.get("name") and inp.get("value") is not None:
            fields[inp["name"]] = inp["value"]
    return action, fields


class PaymentProcessor:
    """
    Drives the full payment flow for a single checkout.
    Uses the task's existing HttpClient session (same proxy = same IP for Paydock).
    """

    def __init__(self, client: HttpClient, task_name: str, sku: str, log_fn=None):
        self._client = client
        self._task_name = task_name
        self._sku = sku
        self._log = log_fn or (lambda lvl, msg, step="": None)

    async def _log_info(self, msg: str, step: str = "TOKENIZING_CARD") -> None:
        await self._log("info", msg, step)

    async def _log_error(self, msg: str, step: str = "TOKENIZING_CARD") -> None:
        await self._log("error", msg, step)

    # ── Step 1: Tokenise card ─────────────────────────────────────────────────

    async def tokenise_card(self, card: Card) -> str:
        """POST card data to Paydock → returns one-time token string."""
        await self._log_info(f"Tokenising card: {card.alias} (•••• {card.number[-4:]})")
        payload = json.dumps(_card_payload(card))
        resp = await self._client.post(
            PAYDOCK_TOKEN_URL,
            data=payload,
            headers={
                "content-type": "application/json",
                "x-user-public-key": PAYDOCK_PUBLIC_KEY,
            },
        )
        if not resp:
            raise RuntimeError("No response from Paydock tokenisation")
        data = resp.json()
        token = data.get("resource", {}).get("data")
        if not token:
            raise RuntimeError(f"Paydock tokenisation failed: {data}")
        await self._log_info(f"Card tokenised: {token[:20]}...")
        return token

    # ── Step 2: Create 3DS token via Kmart GraphQL ────────────────────────────

    async def create_3ds_token(self, one_time_token: str) -> dict:
        """POST create3DSToken → decode JWT → return tokenData dict."""
        await self._log_info("Creating 3DS token...", step="CREATING_3DS_TOKEN")
        resp = await self._client.post_json(gql.KMART_GRAPHQL, gql.create_3ds_token(one_time_token))
        if not resp:
            raise RuntimeError("No response from create3DSToken")
        body = resp.json()
        if "errors" in body:
            msg = body["errors"][0].get("message", "Unknown error")
            raise RuntimeError(f"create3DSToken error: {msg}")
        raw_token = body.get("data", {}).get("create3DSToken")
        if not raw_token:
            raise RuntimeError(f"No token in create3DSToken response: {body}")
        token_data = _decode_3ds_jwt(raw_token)
        await self._log_info("3DS token decoded", step="CREATING_3DS_TOKEN")
        return token_data

    # ── Step 3: 3DS initialization form chain ────────────────────────────────

    async def _run_3ds_form_chain(self, token_data: dict) -> None:
        """GET init URL and POST the browser fingerprint form chain."""
        import tls_client as tls

        # Use a fresh tls_client session for 3DS — same proxy to match IP
        session = tls.Session(client_identifier="chrome_146", random_tls_extension_order=True)
        session.headers = {
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-site": "cross-site",
            "sec-fetch-mode": "navigate",
            "sec-fetch-dest": "iframe",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
        }
        if self._client.proxy:
            session.proxies = self._client.proxy

        def _sync_chain():
            init_resp = session.get(token_data["initialization_url"])
            if not init_resp or not init_resp.text.strip():
                return

            soup = BeautifulSoup(init_resp.text, "html.parser")
            form = soup.find("form", id="form") or soup.find("form", attrs={"name": "brwInfo"})
            if not form or not form.get("action"):
                return

            action = form["action"].replace("&amp;threeDSMethodTimedOut=true", "")
            fingerprint = {
                "browserTZ": "-600",
                "browserScreenWidth": "1470",
                "browserScreenHeight": "956",
                "browserColorDepth": "30",
                "browserLanguage": "en-GB",
                "browserJavaEnabled": "false",
            }
            r2 = session.post(action, data=fingerprint)

            # Chain: validate → process → final
            for _ in range(3):
                soup2 = BeautifulSoup(r2.text, "html.parser")
                result = _extract_form(soup2)
                if not result:
                    break
                action2, fields2 = result
                r2 = session.post(action2, data=fields2)

        await asyncio.to_thread(_sync_chain)

    # ── Step 4: Poll 3DS process status ──────────────────────────────────────

    async def poll_3ds(self, token_data: dict) -> str:
        """
        Poll Paydock until 3DS status is success.
        Returns the charge_3ds_id to use in the final order submission.
        Raises on non-recoverable failure.
        """
        charge_id = token_data["charge_3ds_id"]
        access_token = token_data["xAccessToken"]

        await self._log_info("Running 3DS form chain...", step="PROCESSING_3DS")
        await self._run_3ds_form_chain(token_data)

        await self._log_info("Polling 3DS status...", step="PROCESSING_3DS")

        for attempt in range(20):
            resp = await self._client.post_json(
                PAYDOCK_3DS_PROCESS_URL,
                {"charge_3ds_id": charge_id},
                extra_headers={"x-access-token": access_token},
            )
            if not resp:
                await asyncio.sleep(5)
                continue

            data = resp.json()
            status = data.get("resource", {}).get("data", {}).get("status", "")

            if status == "success":
                await self._log_info("3DS authenticated successfully", step="PROCESSING_3DS")
                return charge_id

            elif status == "pending":
                challenge_url = (
                    data.get("resource", {}).get("data", {}).get("result", {}).get("challenge_url")
                )
                if challenge_url:
                    await self._log("warn", f"3DS challenge required: {challenge_url}", "PROCESSING_3DS")
                    await notify_challenge(self._task_name, self._sku, challenge_url)
                await self._log_info("3DS pending — waiting 30s...", step="PROCESSING_3DS")
                await asyncio.sleep(30)

            else:
                raise RuntimeError(f"3DS failed with status: {status!r} — {data}")

        raise RuntimeError("3DS polling timed out after 20 attempts")
