"""
Persistent key-value settings endpoint.
Settings are stored in the `settings` table and overlaid on top of config.json values.
"""

from fastapi import APIRouter, Depends
from typing import Dict
import aiosqlite

from backend.database import get_db
from backend.config import apply_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=Dict[str, str])
async def get_settings(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT key, value FROM settings") as cur:
        rows = await cur.fetchall()
    return {row["key"]: row["value"] for row in rows}


@router.put("", response_model=Dict[str, str])
async def save_settings(
    body: Dict[str, str], db: aiosqlite.Connection = Depends(get_db)
):
    for key, value in body.items():
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    apply_settings(body)
    return body
