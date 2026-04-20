"""
WebSocket endpoint — single connection point for the dashboard.
_broadcast is registered on the event bus by main.py lifespan (not here),
since APIRouter.on_event is deprecated in FastAPI 0.95+.
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Registry of active WebSocket connections
_clients: set[WebSocket] = set()


async def _broadcast(event: dict) -> None:
    """Send an event to every connected client. Remove dead connections."""
    dead = set()
    for ws in _clients:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    try:
        # Keep the connection alive — we only send, never expect messages
        while True:
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _clients.discard(ws)
