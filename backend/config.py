"""
Application configuration loaded from config.json at project root.
All settings are optional with sensible defaults.
"""

import json
from pathlib import Path
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
