"""
Runs a single task end-to-end.
Instantiates the correct site bot, wires up the log emitter, persists results.
Called exclusively by TaskManager — never directly.
"""

import asyncio
import json
from datetime import datetime, timezone

import aiosqlite

from backend.database import DB_PATH
from backend.models.task import Task, TaskStatus
from backend.core import event_bus
from backend.services import discord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def _update_task_status(
    db: aiosqlite.Connection,
    task_id: str,
    status: str,
    error_message: str = "",
    order_number: str = "",
) -> None:
    await db.execute(
        "UPDATE tasks SET status=?, error_message=?, order_number=?, updated_at=? WHERE id=?",
        (status, error_message or None, order_number or None, _now(), task_id),
    )
    await db.commit()


async def _write_log(
    db: aiosqlite.Connection,
    task_id: str,
    level: str,
    message: str,
    step: str,
) -> None:
    await db.execute(
        "INSERT INTO task_logs (task_id, level, message, step) VALUES (?, ?, ?, ?)",
        (task_id, level, message, step),
    )
    await db.commit()


async def run_task(task_id: str) -> None:
    """
    Full lifecycle for a single task.
    Designed to run as an asyncio.Task — CancelledError is caught, status set to STOPPED.
    """
    db = await _get_db()

    try:
        # Load task record
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return
        task = Task.from_row(row)

        # Load profile
        async with db.execute("SELECT * FROM profiles WHERE id = ?", (task.profile_id,)) as cur:
            prow = await cur.fetchone()
        if not prow:
            await _update_task_status(db, task_id, TaskStatus.FAILED, "Profile not found")
            return
        from backend.models.profile import Profile
        profile = Profile.from_row(prow)

        # Load first card from card_ids list
        card_ids = json.loads(row["card_ids"] or "[]")
        if not card_ids:
            await _update_task_status(db, task_id, TaskStatus.FAILED, "No cards assigned")
            return

        from backend.models.card import Card
        async with db.execute("SELECT * FROM cards WHERE id = ?", (card_ids[0],)) as cur:
            crow = await cur.fetchone()
        if not crow:
            await _update_task_status(db, task_id, TaskStatus.FAILED, "Card not found")
            return
        card = Card.from_row(crow)

        # Mark as running
        await _update_task_status(db, task_id, TaskStatus.RUNNING)
        await event_bus.publish(event_bus.task_update_event(task_id, TaskStatus.RUNNING))

        # Build log emitter — writes to DB and broadcasts via event bus
        async def log_fn(level: str, message: str, step: str = "") -> None:
            await _write_log(db, task_id, level, message, step)
            await event_bus.publish(event_bus.task_log_event(task_id, level, message, step))
            if step:
                await event_bus.publish(event_bus.task_update_event(task_id, TaskStatus.RUNNING, step=step))

        # Instantiate the correct site bot
        bot = _make_bot(task, profile, card, log_fn)

        # Run
        order_number = await bot.run()

        # Success
        await _update_task_status(db, task_id, TaskStatus.SUCCESS, order_number=order_number)
        await event_bus.publish(
            event_bus.task_update_event(task_id, TaskStatus.SUCCESS, order_number=order_number)
        )

    except asyncio.CancelledError:
        await _update_task_status(db, task_id, TaskStatus.STOPPED)
        await event_bus.publish(event_bus.task_update_event(task_id, TaskStatus.STOPPED))

    except Exception as exc:
        reason = str(exc)
        await _update_task_status(db, task_id, TaskStatus.FAILED, error_message=reason)
        await event_bus.publish(
            event_bus.task_update_event(task_id, TaskStatus.FAILED, error_message=reason)
        )
        await discord.notify_failure(task.name or task.sku, task.sku, reason)

    finally:
        await db.close()


def _make_bot(task: Task, profile, card, log_fn):
    """Factory — returns the correct BaseSite subclass for task.site."""
    if task.site == "kmart":
        from backend.sites.kmart.bot import KmartBot
        return KmartBot(task, profile, card, log_fn)
    raise ValueError(f"Unknown site: {task.site!r}")
