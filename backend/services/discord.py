"""Discord webhook notifications for checkout events."""

import asyncio
import aiohttp
from typing import Optional

from backend.config import config


async def _send_webhook(url: str, payload: dict) -> bool:
    if not url:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status in (200, 204)
    except Exception:
        return False


def _success_embed(task_name: str, sku: str, order_number: str, product_name: str = "") -> dict:
    return {
        "embeds": [{
            "title": "✅ Checkout Success",
            "color": 0x00FF7F,
            "fields": [
                {"name": "Task", "value": task_name or sku, "inline": True},
                {"name": "SKU", "value": sku, "inline": True},
                {"name": "Order", "value": order_number, "inline": True},
                {"name": "Product", "value": product_name or "—", "inline": False},
            ],
        }]
    }


def _failure_embed(task_name: str, sku: str, reason: str) -> dict:
    return {
        "embeds": [{
            "title": "❌ Checkout Failed",
            "color": 0xFF4444,
            "fields": [
                {"name": "Task", "value": task_name or sku, "inline": True},
                {"name": "SKU", "value": sku, "inline": True},
                {"name": "Reason", "value": reason[:1024], "inline": False},
            ],
        }]
    }


def _challenge_embed(task_name: str, sku: str, challenge_url: str) -> dict:
    return {
        "embeds": [{
            "title": "⚠️ 3DS Challenge Required",
            "color": 0xFFAA00,
            "description": "Manual action needed — complete the 3DS challenge to proceed.",
            "fields": [
                {"name": "Task", "value": task_name or sku, "inline": True},
                {"name": "SKU", "value": sku, "inline": True},
                {"name": "URL", "value": challenge_url[:1024], "inline": False},
            ],
        }]
    }


async def notify_success(task_name: str, sku: str, order_number: str, product_name: str = "") -> None:
    await _send_webhook(config.webhook_url, _success_embed(task_name, sku, order_number, product_name))


async def notify_failure(task_name: str, sku: str, reason: str) -> None:
    await _send_webhook(config.webhook_url, _failure_embed(task_name, sku, reason))


async def notify_challenge(task_name: str, sku: str, challenge_url: str) -> None:
    await _send_webhook(
        config.challenge_webhook_url or config.webhook_url,
        _challenge_embed(task_name, sku, challenge_url),
    )
