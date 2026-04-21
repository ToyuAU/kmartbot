"""
Runs a single task end-to-end.
Instantiates the correct site bot, wires up the log emitter, persists results.
Called exclusively by TaskManager — never directly.
"""

import asyncio
import json
from datetime import datetime, timezone

import aiosqlite

from backend.database import connect_db
from backend.models.task import Task, TaskStatus
from backend.core import event_bus
from backend.services import discord
from backend.services.analytics import TaskAnalyticsRecorder


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_db() -> aiosqlite.Connection:
    return await connect_db()


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


async def _clear_logs(db: aiosqlite.Connection, task_id: str) -> None:
    await db.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))


def _proxy_label(proxy: dict | None) -> str:
    if not proxy:
        return ""
    return proxy.get("https") or proxy.get("http") or ""


async def run_task(task_id: str) -> None:
    """
    Full lifecycle for a single task.
    Designed to run as an asyncio.Task — CancelledError is caught, status set to STOPPED.
    """
    db = await _get_db()
    task: Task | None = None
    analytics: TaskAnalyticsRecorder | None = None

    try:
        # Load task record
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return
        task = Task.from_row(row)
        card_ids = json.loads(row["card_ids"] or "[]")
        primary_card_id = card_ids[0] if card_ids else ""

        analytics = await TaskAnalyticsRecorder.create(
            db,
            task=task,
            primary_card_id=primary_card_id,
        )

        # Each start should present a fresh run log stream.
        await _clear_logs(db, task_id)
        await analytics.record_status("preparing")
        await db.commit()

        # Load profile
        async with db.execute("SELECT * FROM profiles WHERE id = ?", (task.profile_id,)) as cur:
            prow = await cur.fetchone()
        if not prow:
            await _update_task_status(db, task_id, TaskStatus.FAILED, "Profile not found")
            await analytics.finish(TaskStatus.FAILED, error_message="Profile not found")
            await db.commit()
            await event_bus.publish(
                event_bus.task_update_event(task_id, TaskStatus.FAILED, error_message="Profile not found")
            )
            return
        from backend.models.profile import Profile
        profile = Profile.from_row(prow)

        # Load first card from card_ids list
        if not card_ids:
            await _update_task_status(db, task_id, TaskStatus.FAILED, "No cards assigned")
            await analytics.finish(TaskStatus.FAILED, error_message="No cards assigned")
            await db.commit()
            await event_bus.publish(
                event_bus.task_update_event(task_id, TaskStatus.FAILED, error_message="No cards assigned")
            )
            return

        from backend.models.card import Card
        async with db.execute("SELECT * FROM cards WHERE id = ?", (card_ids[0],)) as cur:
            crow = await cur.fetchone()
        if not crow:
            await _update_task_status(db, task_id, TaskStatus.FAILED, "Card not found")
            await analytics.finish(TaskStatus.FAILED, error_message="Card not found")
            await db.commit()
            await event_bus.publish(
                event_bus.task_update_event(task_id, TaskStatus.FAILED, error_message="Card not found")
            )
            return
        card = Card.from_row(crow)

        # Instantiate the correct site bot
        async def log_fn(level: str, message: str, step: str = "") -> None:
            ts = _now()
            await _write_log(db, task_id, level, message, step)
            await analytics.record_log(level, message, step=step, ts=ts)
            await db.commit()
            await event_bus.publish(event_bus.task_log_event(task_id, level, message, step))
            if step:
                await event_bus.publish(event_bus.task_update_event(task_id, TaskStatus.RUNNING, step=step))

        bot = _make_bot(task, profile, card, log_fn)
        await analytics.update_summary(
            card_alias=card.alias,
            proxy=_proxy_label(getattr(bot, "_client", None).proxy if hasattr(bot, "_client") else None),
        )

        # Mark as running
        await _update_task_status(db, task_id, TaskStatus.RUNNING)
        await analytics.record_status(TaskStatus.RUNNING)
        await db.commit()
        await event_bus.publish(event_bus.task_update_event(task_id, TaskStatus.RUNNING))

        # Run
        order_number = await bot.run()

        # Success
        await _update_task_status(db, task_id, TaskStatus.SUCCESS, order_number=order_number)
        await analytics.finish(TaskStatus.SUCCESS, order_number=order_number)
        await db.commit()
        await event_bus.publish(
            event_bus.task_update_event(task_id, TaskStatus.SUCCESS, order_number=order_number)
        )

    except asyncio.CancelledError:
        await _update_task_status(db, task_id, TaskStatus.STOPPED)
        if analytics:
            await analytics.finish(TaskStatus.STOPPED)
        await db.commit()
        await event_bus.publish(event_bus.task_update_event(task_id, TaskStatus.STOPPED))

    except Exception as exc:
        reason = str(exc)
        await _update_task_status(db, task_id, TaskStatus.FAILED, error_message=reason)
        if analytics:
            await analytics.finish(TaskStatus.FAILED, error_message=reason)
        await db.commit()
        await event_bus.publish(
            event_bus.task_update_event(task_id, TaskStatus.FAILED, error_message=reason)
        )
        if task is not None:
            await discord.notify_failure(task.name or task.sku, task.sku, reason)

    finally:
        await db.close()


def _make_bot(task: Task, profile, card, log_fn):
    """Factory — returns the correct BaseSite subclass for task.site."""
    if task.site == "kmart":
        from backend.sites.kmart.bot import KmartBot
        return KmartBot(task, profile, card, log_fn)
    raise ValueError(f"Unknown site: {task.site!r}")
