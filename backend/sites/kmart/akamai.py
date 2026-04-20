"""
Akamai bypass for kmart.com.au using hyper_sdk.
Ported and cleaned from kmartbot-main/Classes/SafeRequestV2.py.

Wraps the synchronous hyper_sdk calls with asyncio.to_thread() so they
don't block the event loop.
"""

import asyncio
import json
import re
import time
import random
from typing import Optional
from urllib.parse import urlparse

from hyper_sdk import Session as HyperSession, SensorInput, SbsdInput
from hyper_sdk.akamai import parse_akamai_script_path, is_cookie_valid, is_cookie_invalidated

from backend.services.http_client import HttpClient

HYPER_API_KEY = "88e24b72-251d-4359-85ac-c0c301db5f38"
AKAMAI_VERSION = "3"
KMART_HOME = "https://www.kmart.com.au/"
SBSD_REGEX = re.compile(r'(?i)([a-z\d/\-_\.]+)\?v=(.*?)(?:&.*?t=(.*?))?["\']')

MAX_SENSOR_ATTEMPTS = 5
MAX_PROXY_ROTATIONS = 3


class _SbsdInfo:
    def __init__(self, path: str, uuid: str, t: str = ""):
        self.path = path
        self.uuid = uuid
        self.t = t

    def is_hardblock(self) -> bool:
        return bool(self.t)

    def script_url(self, base: str) -> str:
        p = urlparse(base)
        url = f"{p.scheme}://{p.netloc}{self.path}?v={self.uuid}"
        if self.t:
            url += f"&t={self.t}"
        return url

    def post_url(self, base: str) -> str:
        p = urlparse(base)
        url = f"{p.scheme}://{p.netloc}{self.path}"
        if self.t:
            url += f"?t={self.t}"
        return url


def _parse_sbsd(html: str) -> Optional[_SbsdInfo]:
    m = SBSD_REGEX.search(html)
    if not m:
        return None
    info = _SbsdInfo(path=m.group(1), uuid=m.group(2))
    if m.group(3):
        info.t = m.group(3)
    return info


class AkamaiSolver:
    """
    Drives the full Akamai solve for a single tls_client session.
    One instance per HttpClient instance — never share.
    """

    def __init__(self, client: HttpClient, log_fn=None):
        self._client = client
        self._log = log_fn or (lambda *a: None)
        self._hyper = HyperSession(api_key=HYPER_API_KEY)
        self._ip: str = ""
        self._page_html: str = ""
        self._sensor_endpoint: str = ""
        self._sensor_script: str = ""
        self._sensor_context: str = ""
        self._sbsd_info: Optional[_SbsdInfo] = None
        self._sbsd_script: str = ""
        self._sbsd_script_cache: dict = {}
        self._proxy_rotations: int = 0

    def _log_info(self, msg: str) -> None:
        if callable(self._log):
            try:
                # Support both sync and async log callables
                import inspect
                if inspect.iscoroutinefunction(self._log):
                    asyncio.create_task(self._log("info", msg, "SOLVING_AKAMAI"))
                else:
                    self._log("info", msg, "SOLVING_AKAMAI")
            except Exception:
                pass

    # ── Sync internals (run in thread via to_thread) ──────────────────────────

    def _get_ip_sync(self) -> str:
        try:
            r = self._client._get_sync("https://api.ipify.org")
            return r.text.strip()
        except Exception:
            return ""

    def _fetch_page_sync(self) -> str:
        r = self._client._get_sync(KMART_HOME)
        html = r.text if r else ""
        self._page_html = html
        self._sbsd_info = _parse_sbsd(html)
        return html

    def _fetch_sbsd_script_sync(self) -> bool:
        url = self._sbsd_info.script_url(KMART_HOME)
        cached = self._sbsd_script_cache.get(url)
        if cached:
            self._sbsd_script = cached
            return True
        try:
            r = self._client._get_sync(url)
            if r and r.status_code == 200 and r.text:
                self._sbsd_script = r.text
                self._sbsd_script_cache[url] = r.text
                return True
        except Exception:
            pass
        return False

    def _post_sbsd_sync(self, index: int) -> bool:
        o_cookie = self._client.get_cookie("bm_so") or self._client.get_cookie("sbsd_o")
        try:
            payload = self._hyper.generate_sbsd_data(
                SbsdInput(
                    index=index,
                    user_agent=self._client._session.headers.get("user-agent", ""),
                    uuid=self._sbsd_info.uuid,
                    page_url=KMART_HOME,
                    o_cookie=o_cookie,
                    script=self._sbsd_script,
                    accept_language="en-US,en;q=0.9",
                    ip=self._ip,
                )
            )
            body = json.dumps({"body": payload})
            r = self._client._post_sync(self._sbsd_info.post_url(KMART_HOME), data=body)
            return r is not None and r.status_code in (200, 201, 202, 204)
        except Exception:
            return False

    def _post_sensor_sync(self, iteration: int) -> bool:
        try:
            abck = self._client.get_cookie("_abck")
            bmsz = self._client.get_cookie("bm_sz")

            sensor_data, ctx = self._hyper.generate_sensor_data(
                SensorInput(
                    abck=abck,
                    bmsz=bmsz,
                    version=AKAMAI_VERSION,
                    page_url=KMART_HOME,
                    user_agent=self._client._session.headers.get("user-agent", ""),
                    script_url=self._sensor_endpoint,
                    accept_language="en-US,en;q=0.9",
                    ip=self._ip,
                    context=self._sensor_context,
                    script=self._sensor_script if iteration == 0 else "",
                )
            )
            self._sensor_context = ctx

            body = json.dumps({"sensor_data": sensor_data})
            r = self._client._post_sync(self._sensor_endpoint, data=body)
            return r is not None and r.status_code in (200, 201, 202, 204)
        except Exception:
            return False

    def _solve_sync(self) -> bool:
        """Full synchronous Akamai solve — called via to_thread."""
        # Check if cookie already valid
        abck = self._client.get_cookie("_abck")
        if abck and is_cookie_valid(abck, 0):
            return True

        self._sensor_context = ""

        # Get IP
        if not self._ip:
            self._ip = self._get_ip_sync()

        # Fetch page + detect SBSD
        self._fetch_page_sync()

        # SBSD challenge
        if self._sbsd_info:
            if self._fetch_sbsd_script_sync():
                if self._sbsd_info.is_hardblock():
                    self._post_sbsd_sync(0)
                    self._fetch_page_sync()
                else:
                    self._post_sbsd_sync(0)
                    self._post_sbsd_sync(1)

        # Parse sensor endpoint
        try:
            script_path = parse_akamai_script_path(self._page_html)
            p = urlparse(KMART_HOME)
            self._sensor_endpoint = f"{p.scheme}://{p.netloc}{script_path}"
        except Exception:
            return True  # no sensor endpoint found — proceed anyway

        # Fetch sensor script
        try:
            r = self._client._get_sync(self._sensor_endpoint)
            self._sensor_script = r.text if r else ""
        except Exception:
            pass

        # Post sensors
        for i in range(MAX_SENSOR_ATTEMPTS):
            delay = random.uniform(0.8, 1.5)
            time.sleep(delay)

            if not self._post_sensor_sync(i):
                break

            abck = self._client.get_cookie("_abck")
            if abck and (is_cookie_valid(abck, i) or is_cookie_valid(abck, 0)):
                return True

            if i >= 2:
                break  # min 3 attempts

        # Proceed optimistically even if cookie wasn't validated
        return True

    # ── Async public interface ────────────────────────────────────────────────

    async def solve(self) -> bool:
        """
        Attempt Akamai bypass. Returns True when the session has valid cookies.
        Rotates proxy and retries on failure (up to MAX_PROXY_ROTATIONS times).
        """
        for attempt in range(MAX_PROXY_ROTATIONS + 1):
            ok = await asyncio.to_thread(self._solve_sync)
            if ok:
                return True
            if attempt < MAX_PROXY_ROTATIONS:
                self._client.rotate_proxy()
                self._client.clear_cookies()
                self._sensor_context = ""
                self._proxy_rotations += 1
        return False

    def close(self) -> None:
        try:
            self._hyper.close()
        except Exception:
            pass
