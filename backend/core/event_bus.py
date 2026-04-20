"""
Internal event bus — bots publish events here, the WebSocket hub subscribes
and broadcasts to all connected dashboard clients.

All events are plain dicts serialised as JSON over the wire.
"""

import asyncio
from typing import Callable, Awaitable, Any

# Type for an async event handler
Handler = Callable[[dict], Awaitable[None]]

_subscribers: list[Handler] = []


def subscribe(handler: Handler) -> None:
    """Register a coroutine to receive all published events."""
    _subscribers.append(handler)


def unsubscribe(handler: Handler) -> None:
    try:
        _subscribers.remove(handler)
    except ValueError:
        pass


async def publish(event: dict) -> None:
    """
    Publish an event to all subscribers concurrently.
    Exceptions in individual handlers are silently swallowed to avoid
    killing a task because one WebSocket client disconnected.
    """
    if not _subscribers:
        return
    await asyncio.gather(*[h(event) for h in _subscribers], return_exceptions=True)


# ── Convenience constructors ──────────────────────────────────────────────────

def task_log_event(task_id: str, level: str, message: str, step: str = "") -> dict:
    from datetime import datetime, timezone
    return {
        "type": "task_log",
        "task_id": task_id,
        "level": level,
        "message": message,
        "step": step,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def task_update_event(task_id: str, status: str, step: str = "", **extra) -> dict:
    return {"type": "task_update", "task_id": task_id, "status": status, "step": step, **extra}
