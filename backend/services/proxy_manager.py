"""
Proxy pool manager.
Loads proxies from data/proxies.txt on first use and rotates through them.

Supported formats:
    host:port
    host:port:user:pass
    user:pass@host:port
"""

import random
from pathlib import Path
from typing import Optional

PROXY_FILE = Path(__file__).parent.parent.parent / "data" / "proxies.txt"


def _parse_proxy(line: str) -> Optional[dict]:
    """Parse a single proxy line into a dict suitable for tls_client."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # user:pass@host:port
    if "@" in line:
        creds, hostport = line.rsplit("@", 1)
        user, password = creds.split(":", 1)
        host, port = hostport.rsplit(":", 1)
        url = f"http://{user}:{password}@{host}:{port}"
    else:
        parts = line.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            url = f"http://{user}:{password}@{host}:{port}"
        elif len(parts) == 2:
            url = f"http://{line}"
        else:
            return None

    return {"http": url, "https": url}


class ProxyManager:
    _proxies: list[dict] = []
    _loaded: bool = False

    @classmethod
    def _load(cls) -> None:
        if cls._loaded:
            return
        cls._loaded = True
        if not PROXY_FILE.exists():
            return
        for line in PROXY_FILE.read_text().splitlines():
            parsed = _parse_proxy(line)
            if parsed:
                cls._proxies.append(parsed)

    @classmethod
    def get(cls, random_pick: bool = True) -> Optional[dict]:
        """Return a proxy dict, or None if the list is empty."""
        cls._load()
        if not cls._proxies:
            return None
        return random.choice(cls._proxies) if random_pick else cls._proxies[0]

    @classmethod
    def count(cls) -> int:
        cls._load()
        return len(cls._proxies)
