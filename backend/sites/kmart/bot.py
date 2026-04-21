"""
KmartBot — orchestrates the full checkout flow for a single task.

Steps:
  1. Solve Akamai
  2. Create cart
  3. Add to cart
  4. Set shipping + billing
  5. Apply staff code (optional)
  6. Apply Flybuys (optional)
  7. Tokenise card
  8. Create 3DS token
  9. Run 3DS form chain + poll
  10. Submit order

Each step emits structured log events via self.log().
Retries use exponential backoff. asyncio.CancelledError propagates up cleanly.
"""

import asyncio
import random
import re
from collections import deque
from pathlib import Path
from typing import Optional

# Matches Kmart's "...maximum purchase limits(N)" wording in any error message.
_QUANTITY_LIMIT_RE = re.compile(r'maximum\s+purchase\s+limits?\s*\((\d+)\)', re.I)

from backend.sites.base import BaseSite, LogFn
from backend.services.http_client import HttpClient
from backend.services import discord
from backend.models.task import Task
from backend.models.profile import Profile
from backend.models.card import Card
from backend.config import config as app_config

from .akamai import AkamaiSolver
from .payment import PaymentProcessor
import backend.sites.kmart.graphql as gql

STAFF_CODES_FILE = Path(__file__).parent.parent.parent.parent / "data" / "staff_codes.txt"

# Module-level staff code pool — shared across all KmartBot instances
_staff_codes: Optional[deque] = None


def _load_staff_codes() -> deque:
    global _staff_codes
    if _staff_codes:
        return _staff_codes
    codes: list[str] = []
    if STAFF_CODES_FILE.exists():
        for line in STAFF_CODES_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                codes.append(line)
    random.shuffle(codes)
    # Only cache a non-empty pool — otherwise re-read the file on next call
    # so adding codes to staff_codes.txt doesn't require a backend restart.
    if codes:
        _staff_codes = deque(codes)
        return _staff_codes
    return deque()


def _next_staff_code() -> Optional[str]:
    pool = _load_staff_codes()
    if not pool:
        return None
    code = pool.popleft()
    pool.append(code)  # rotate back to end
    return code


class KmartBot(BaseSite):

    GRAPHQL = gql.KMART_GRAPHQL

    def __init__(self, task: Task, profile: Profile, card: Card, log_fn: LogFn):
        super().__init__(task, profile, card, log_fn)
        self._client = HttpClient()
        self._akamai = AkamaiSolver(self._client, log_fn=self._emit_log)
        self._payment = PaymentProcessor(
            self._client,
            task_name=task.name or task.sku,
            sku=task.sku,
            log_fn=log_fn,
        )
        self._cart_id: str = ""
        self._cart_version: int = 0
        self._product_data: dict = {}
        # Set to True once we've already clamped the quantity to a discovered max,
        # so a second checkout failure with the same wording triggers a real abort.
        self._qty_clamped: bool = False

    async def _emit_log(self, level: str, message: str, step: str = "") -> None:
        await self._log(level, message, step)

    # ── Retry helper ──────────────────────────────────────────────────────────

    async def _with_retry(self, coro_fn, step: str, max_attempts: int = 3):
        """Call an async function up to max_attempts times with exponential backoff."""
        last_exc = None
        for attempt in range(max_attempts):
            try:
                return await coro_fn()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                wait = (2 ** attempt) + random.uniform(0, 1)
                await self.warn(f"{step} failed (attempt {attempt + 1}/{max_attempts}): {e}. Retrying in {wait:.1f}s", step)
                await asyncio.sleep(wait)
        raise RuntimeError(f"{step} failed after {max_attempts} attempts: {last_exc}") from last_exc

    # ── Step implementations ───────────────────────────────────────────────────

    async def _solve_akamai(self) -> None:
        await self.info("Solving Akamai...", step="SOLVING_AKAMAI")
        ok = await self._akamai.solve()
        if not ok:
            raise RuntimeError("Akamai bypass failed")
        await self.info("Akamai solved", step="SOLVING_AKAMAI")

    async def _create_cart(self) -> None:
        await self.info("Creating cart...", step="CREATING_CART")
        resp = await self._client.post_json(
            self.GRAPHQL,
            gql.create_cart(
                city=self.profile.city or "Glen Waverley",
                postcode=self.profile.postcode or "3150",
            ),
        )
        if not resp:
            raise RuntimeError("No response from createMyBag")
        body = resp.json()
        cart = body.get("data", {}).get("createMyCart", {})
        self._cart_id = cart.get("id", "")
        self._cart_version = cart.get("version", 0)
        if not self._cart_id:
            raise RuntimeError(f"createMyBag returned no cart id: {body}")
        await self.info(f"Cart created: {self._cart_id}", step="CREATING_CART")

    async def _add_to_cart(self) -> None:
        await self.info(f"Adding SKU {self.task.sku} to cart...", step="ADDING_TO_CART")
        resp = await self._client.post_json(
            self.GRAPHQL,
            gql.add_to_cart(self._cart_id, self.task.sku, self.task.quantity),
        )
        if not resp:
            raise RuntimeError("No response from updateMyBag")
        body = resp.json()
        if "errors" in body:
            msg = body["errors"][0].get("message", "")
            # Quantity limit error — extract max qty and retry with that value
            m = _QUANTITY_LIMIT_RE.search(msg)
            if m:
                max_qty = int(m.group(1))
                self.task.quantity = max_qty
                self._qty_clamped = True
                await self.warn(f"Quantity limit: {max_qty}. Retrying with {max_qty}.", step="ADDING_TO_CART")
                resp2 = await self._client.post_json(
                    self.GRAPHQL,
                    gql.add_to_cart(self._cart_id, self.task.sku, max_qty),
                )
                if not resp2:
                    raise RuntimeError("Retry ATC after quantity limit failed")
                body = resp2.json()
                if "errors" in body:
                    raise RuntimeError(f"ATC still failing after qty fix: {body['errors'][0].get('message')}")
            else:
                raise RuntimeError(f"updateMyBag error: {msg}")

        cart = body.get("data", {}).get("updateMyCart", {})
        self._cart_version = cart.get("version", self._cart_version)
        items = cart.get("lineItems", [])
        self._product_data = items[0] if items else {}
        name = self._product_data.get("name", "")
        await self.info(f"Added to cart: {name or self.task.sku}", step="ADDING_TO_CART")

    async def _set_shipping(self) -> None:
        await self.info("Setting shipping and billing address...", step="SETTING_SHIPPING")
        config_dict = {
            "use_gmail_spoofing": app_config.use_gmail_spoofing,
            "gmail_spoofing_email": app_config.gmail_spoofing_email,
            "catchall_domain": app_config.catchall_domain,
        }
        email, payload = gql.set_shipping(self._cart_id, self.profile, config_dict)
        # Patch version
        payload["variables"]["version"] = self._cart_version

        resp = await self._client.post_json(self.GRAPHQL, payload)
        if not resp:
            raise RuntimeError("No response from updateMyBagWithoutBagStockAvailability (shipping)")
        body = resp.json()
        if "errors" in body:
            raise RuntimeError(f"set_shipping error: {body['errors'][0].get('message')}")
        cart = body.get("data", {}).get("updateMyCart", {})
        self._cart_version = cart.get("version", self._cart_version)
        await self.info(f"Shipping set (email: {email})", step="SETTING_SHIPPING")

    async def _apply_staff_code(self) -> None:
        code = _next_staff_code()
        if not code:
            await self.warn("No staff codes available, skipping.", step="APPLYING_STAFF_CODE")
            return
        await self.info(f"Applying staff code: {code[:4]}****", step="APPLYING_STAFF_CODE")
        resp = await self._client.post_json(self.GRAPHQL, gql.apply_staff_code(code))
        if not resp:
            await self.warn("Staff code response was empty, continuing.", step="APPLYING_STAFF_CODE")
            return
        body = resp.json()
        if "errors" in body:
            await self.warn(f"Staff code error: {body['errors'][0].get('message')}", step="APPLYING_STAFF_CODE")
        else:
            await self.info("Staff code applied", step="APPLYING_STAFF_CODE")

    async def _apply_flybuys(self) -> None:
        if not self.profile.flybuys:
            return
        await self.info(f"Applying Flybuys: {self.profile.flybuys}", step="APPLYING_FLYBUYS")
        resp = await self._client.post_json(
            self.GRAPHQL,
            gql.apply_flybuys(self._cart_id, self._cart_version, self.profile.flybuys),
        )
        if not resp:
            await self.warn("Flybuys response was empty, continuing.", step="APPLYING_FLYBUYS")
            return
        body = resp.json()
        if "errors" in body:
            await self.warn(f"Flybuys error: {body['errors'][0].get('message')}", step="APPLYING_FLYBUYS")
        else:
            cart = body.get("data", {}).get("updateMyCart", {})
            self._cart_version = cart.get("version", self._cart_version)
            await self.info("Flybuys applied", step="APPLYING_FLYBUYS")

    async def _watch_stock(self) -> None:
        """
        Poll refreshMyCart.bagStockAvailability until HOME_DELIVERY bucket is shippable.
        Runs indefinitely — only exits when stock is available or the task is cancelled.

        Bluesamyou: this is the real "can I check out" signal. `isAvailable` on the product
        query lies when the item is in-store only. `bucketType == "OOS"` is the truth.
        """
        await self.info("Watching for shipping stock...", step="WATCHING_STOCK")
        consecutive_errors = 0
        poll_count = 0
        last_bucket: Optional[str] = None

        while True:
            try:
                resp = await self._client.post_json(self.GRAPHQL, gql.refresh_bag_with_availability())
                if not resp:
                    raise RuntimeError("refreshMyBag returned no response")
                body = resp.json()
                if "errors" in body:
                    raise RuntimeError(f"refreshMyBag error: {body['errors'][0].get('message')}")

                cart = body.get("data", {}).get("refreshMyCart", {})
                self._cart_version = cart.get("version", self._cart_version)
                bucket_info = (
                    cart.get("bagStockAvailability", {}) or {}
                ).get("BUCKET_INFO", {}) or {}
                home = bucket_info.get("HOME_DELIVERY") or []
                bucket_type = home[0].get("bucketType") if home else "OOS"
                consecutive_errors = 0

                if bucket_type and bucket_type != "OOS":
                    await self.info(
                        f"Stock available ({bucket_type.lower()}) after {poll_count} polls",
                        step="WATCHING_STOCK",
                    )
                    return

                poll_count += 1
                if bucket_type != last_bucket or poll_count % 20 == 0:
                    await self.info(
                        f"Still OOS (poll #{poll_count})",
                        step="WATCHING_STOCK",
                    )
                    last_bucket = bucket_type
            except asyncio.CancelledError:
                raise
            except Exception as e:
                consecutive_errors += 1
                await self.warn(
                    f"Watch poll failed ({consecutive_errors}): {e}",
                    step="WATCHING_STOCK",
                )
                # If the cart looks dead, re-solve Akamai + recreate + re-ATC.
                if consecutive_errors >= 5:
                    await self.warn("Too many errors — rebuilding cart", step="WATCHING_STOCK")
                    try:
                        await self._solve_akamai()
                        await self._create_cart()
                        await self._add_to_cart()
                    except Exception as rebuild_err:
                        await self.warn(f"Cart rebuild failed: {rebuild_err}", step="WATCHING_STOCK")
                    consecutive_errors = 0

            # Jittered poll — 3-8s. Fast enough to catch drops, gentle enough not to trip rate limits.
            await asyncio.sleep(random.uniform(3.0, 8.0))

    async def _checkout_burst(self) -> str:
        """
        Tokenise → 3DS → submit, retrying the whole chain on failure.
        Paydock tokens are one-time use but infinitely re-requestable, so spray-and-pray
        is safe here (Bluesamyou's advice).
        """
        max_attempts = 10
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                await self.info(
                    f"Checkout attempt {attempt}/{max_attempts}",
                    step="TOKENIZING_CARD",
                )
                one_time_token = await self._payment.tokenise_card(self.card)
                token_data = await self._payment.create_3ds_token(one_time_token)
                charge_id = await self._payment.poll_3ds(token_data)
                return await self._submit_order(charge_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                # Unrecoverable — cart is gone. Bail out of watch mode too.
                if "cart" in msg and ("not found" in msg or "invalid" in msg or "expired" in msg):
                    raise
                # Quantity exceeds checkout limit — update the cart line item to
                # the allowed max and re-run the checkout step from scratch.
                # Only attempt this once; a repeat means something else is wrong.
                qty_match = _QUANTITY_LIMIT_RE.search(str(e))
                if qty_match and not self._qty_clamped:
                    max_qty = int(qty_match.group(1))
                    self._qty_clamped = True
                    try:
                        await self._clamp_line_item_quantity(max_qty)
                        continue
                    except Exception as clamp_err:
                        await self.warn(
                            f"Quantity clamp failed: {clamp_err}",
                            step="TOKENIZING_CARD",
                        )
                wait = min(2 ** attempt, 30) + random.uniform(0, 2)
                await self.warn(
                    f"Checkout attempt {attempt} failed: {e}. Retrying in {wait:.1f}s",
                    step="TOKENIZING_CARD",
                )
                await asyncio.sleep(wait)
        raise RuntimeError(f"Checkout burst exhausted after {max_attempts} attempts: {last_exc}")

    async def _clamp_line_item_quantity(self, max_qty: int) -> None:
        """Update the existing cart's line item quantity to max_qty in place.
        Cart, shipping, staff code, and flybuys are preserved — only quantity changes."""
        line_item_id = self._product_data.get("id")
        if not line_item_id:
            raise RuntimeError("Cannot clamp quantity: no line item id on cart")
        await self.warn(
            f"Quantity {self.task.quantity} exceeds checkout limit ({max_qty}). "
            f"Updating cart to quantity={max_qty}.",
            step="TOKENIZING_CARD",
        )
        resp = await self._client.post_json(
            self.GRAPHQL,
            gql.change_line_item_quantity(self._cart_id, line_item_id, max_qty),
        )
        if not resp:
            raise RuntimeError("No response from changeLineItemQuantity")
        body = resp.json()
        if "errors" in body:
            raise RuntimeError(f"changeLineItemQuantity error: {body['errors'][0].get('message')}")
        cart = body.get("data", {}).get("updateMyCart", {})
        self._cart_version = cart.get("version", self._cart_version)
        items = cart.get("lineItems", [])
        if items:
            self._product_data = items[0]
        self.task.quantity = max_qty

    async def _submit_order(self, charge_3ds_id: str) -> str:
        await self.info("Submitting order...", step="SUBMITTING_ORDER")
        resp = await self._client.post_json(self.GRAPHQL, gql.charge_paydock(charge_3ds_id))
        if not resp:
            raise RuntimeError("No response from chargePayDockWithToken")
        body = resp.json()
        if "errors" in body:
            raise RuntimeError(f"chargePayDockWithToken error: {body['errors'][0].get('message')}")
        order = body.get("data", {}).get("chargePayDockWithToken", {})
        order_number = order.get("orderNumber", "")
        if not order_number:
            raise RuntimeError(f"No order number in response: {body}")
        return order_number

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run(self) -> str:
        """
        Execute the full checkout flow.
        Returns the order number on success.
        Raises RuntimeError (or CancelledError) on failure.
        """
        try:
            await self._with_retry(self._solve_akamai, "SOLVING_AKAMAI")
            await self._with_retry(self._create_cart, "CREATING_CART")
            await self._with_retry(self._add_to_cart, "ADDING_TO_CART")

            if self.task.watch_mode:
                # Poll shipping availability on the existing cart until stock drops.
                await self._watch_stock()

            await self._with_retry(self._set_shipping, "SETTING_SHIPPING")

            if self.task.use_staff_codes and app_config.use_staff_codes:
                await self._apply_staff_code()

            if self.task.use_flybuys and self.profile.flybuys:
                await self._apply_flybuys()

            # Payment — token chain retries internally (tokens are one-shot but re-requestable).
            order_number = await self._checkout_burst()

            product_name = self._product_data.get("name", "")
            await self.success(f"Order placed: {order_number}", step="SUCCESS")
            await discord.notify_success(
                self.task.name or self.task.sku,
                self.task.sku,
                order_number,
                product_name,
            )
            return order_number

        finally:
            self._akamai.close()
