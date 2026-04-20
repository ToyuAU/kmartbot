"""
Per-task TLS client.
Wraps tls_client with Chrome 146 fingerprinting.
Each task gets its own instance so cookie jars and proxies are fully isolated.

Note: tls_client is synchronous. Blocking calls are wrapped in asyncio.to_thread()
so they don't block the event loop.
"""

import asyncio
import json as json_lib
from typing import Optional, Any

import tls_client

from backend.services.proxy_manager import ProxyManager


CHROME_BUILD = "chrome_146"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"'
SEC_CH_UA_PLATFORM = '"Windows"'

DEFAULT_HEADERS = {
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": SEC_CH_UA_PLATFORM,
    "upgrade-insecure-requests": "1",
    "user-agent": USER_AGENT,
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://www.kmart.com.au/",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "priority": "u=0, i",
}

HEADER_ORDER = [
    "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
    "upgrade-insecure-requests", "user-agent", "accept",
    "sec-fetch-site", "sec-fetch-mode", "sec-fetch-user", "sec-fetch-dest",
    "referer", "accept-encoding", "accept-language", "priority",
]

PSEUDO_HEADER_ORDER = [":method", ":authority", ":scheme", ":path"]


class HttpClient:
    """
    Synchronous tls_client session exposed with async wrappers.
    One instance per bot task — never share across tasks.
    """

    def __init__(self, proxy: Optional[dict] = None):
        self._session = tls_client.Session(
            client_identifier=CHROME_BUILD,
            random_tls_extension_order=True,
            force_http1=False,
        )
        self._session.timeout_seconds = 30
        self._session.headers = DEFAULT_HEADERS.copy()
        self._session.header_order = HEADER_ORDER
        self._session.pseudo_header_order = PSEUDO_HEADER_ORDER

        self.proxy = proxy or ProxyManager.get()
        if self.proxy:
            self._session.proxies = self.proxy

    # ── Synchronous helpers ───────────────────────────────────────────────────

    def _get_sync(self, url: str, **kwargs) -> Any:
        return self._session.get(url, **kwargs)

    def _post_sync(self, url: str, data: Any = None, headers: dict = None, **kwargs) -> Any:
        kw = dict(kwargs)
        if headers:
            kw["headers"] = headers
        return self._session.post(url, data=data, **kw)

    def _post_json_sync(self, url: str, payload: dict, extra_headers: dict = None) -> Any:
        body = json_lib.dumps(payload)
        headers = {"content-type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        return self._session.post(url, data=body, headers=headers)

    # ── Async wrappers ────────────────────────────────────────────────────────

    async def get(self, url: str, **kwargs) -> Any:
        return await asyncio.to_thread(self._get_sync, url, **kwargs)

    async def post(self, url: str, data: Any = None, headers: dict = None, **kwargs) -> Any:
        return await asyncio.to_thread(self._post_sync, url, data, headers, **kwargs)

    async def post_json(self, url: str, payload: dict, extra_headers: dict = None) -> Any:
        return await asyncio.to_thread(self._post_json_sync, url, payload, extra_headers)

    # ── Cookie helpers ────────────────────────────────────────────────────────

    def get_cookie(self, name: str) -> str:
        return self._session.cookies.get_dict().get(name, "")

    def all_cookies(self) -> dict:
        return self._session.cookies.get_dict()

    def set_cookie(self, name: str, value: str, domain: str = "") -> None:
        self._session.cookies.set(name, value, domain=domain)

    def clear_cookies(self) -> None:
        self._session.cookies.clear()

    # ── Proxy rotation ────────────────────────────────────────────────────────

    def rotate_proxy(self) -> bool:
        new_proxy = ProxyManager.get()
        if new_proxy:
            self.proxy = new_proxy
            self._session.proxies = new_proxy
            return True
        return False

    # ── Session re-init ───────────────────────────────────────────────────────

    def reset(self) -> None:
        """Full session reset — new tls_client, new proxy, cleared state."""
        self.proxy = ProxyManager.get()
        self._session = tls_client.Session(
            client_identifier=CHROME_BUILD,
            random_tls_extension_order=True,
            force_http1=False,
        )
        self._session.timeout_seconds = 30
        self._session.headers = DEFAULT_HEADERS.copy()
        self._session.header_order = HEADER_ORDER
        self._session.pseudo_header_order = PSEUDO_HEADER_ORDER
        if self.proxy:
            self._session.proxies = self.proxy
