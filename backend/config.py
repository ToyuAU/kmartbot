"""
Application configuration loaded from config.json at project root,
then overlaid with values from the SQLite `settings` table at startup
and refreshed whenever the dashboard Settings UI saves new values.
"""

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class Config(BaseModel):
    # Discord webhooks
    webhook_url: str = ""
    challenge_webhook_url: str = ""

    # Email generation
    catchall_domain: str = ""
    use_gmail_spoofing: bool = False
    gmail_spoofing_email: str = ""

    # Features
    use_staff_codes: bool = True
    precheck_shipping: bool = False
    rotate_proxy_on_bot_detection: bool = False

    # Dashboard
    dashboard_port: int = 8080


def load_config() -> Config:
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text())
        return Config(**{k: v for k, v in raw.items() if k in Config.model_fields})
    return Config()


# Module-level singleton — imported everywhere
config = load_config()


def _coerce(field_name: str, raw: str) -> Any:
    """Coerce a string value from the settings table into the Config field's type."""
    field = Config.model_fields.get(field_name)
    if field is None:
        return None
    annotation = field.annotation
    if annotation is bool:
        return str(raw).strip().lower() in ("true", "1", "yes", "on")
    if annotation is int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return raw


def apply_settings(values: dict[str, str]) -> None:
    """Overlay values from the dashboard Settings UI onto the in-memory config singleton.

    Mutates `config` in place so existing imports (`from backend.config import config`)
    see the new values without restart.
    """
    for key, raw in values.items():
        if key not in Config.model_fields:
            continue
        value = _coerce(key, raw)
        if value is None:
            continue
        if key == "catchall_domain" and isinstance(value, str):
            value = value.lstrip("@").strip()
        setattr(config, key, value)
