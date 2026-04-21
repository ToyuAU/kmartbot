"""Structured task-run analytics recorded in SQLite."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(started_at: str, finished_at: str) -> int:
    start = datetime.fromisoformat(started_at)
    end = datetime.fromisoformat(finished_at)
    return max(0, int((end - start).total_seconds() * 1000))


def _json(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class TaskAnalyticsRecorder:
    """Persists run summaries plus the full event stream for one task execution."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        *,
        run_id: str,
        task_id: str,
        started_at: str,
    ) -> None:
        self._db = db
        self.run_id = run_id
        self.task_id = task_id
        self.started_at = started_at
        self._event_seq = 0
        self._current_step: str = ""
        self._current_step_started_at: str = ""
        self._current_step_row_id: int | None = None

    @classmethod
    async def create(
        cls,
        db: aiosqlite.Connection,
        *,
        task,
        primary_card_id: str = "",
        primary_card_alias: str = "",
        proxy: str = "",
    ) -> "TaskAnalyticsRecorder":
        started_at = now_iso()
        run_id = str(uuid.uuid4())
        recorder = cls(db, run_id=run_id, task_id=task.id, started_at=started_at)
        await db.execute(
            """INSERT INTO task_runs
               (id, task_id, task_name, site, sku, profile_id, card_id, card_alias,
                proxy, watch_mode, quantity, started_at, final_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                task.id,
                task.name,
                task.site,
                task.sku,
                task.profile_id,
                primary_card_id,
                primary_card_alias,
                proxy,
                int(task.watch_mode),
                task.quantity,
                started_at,
                "created",
            ),
        )
        await recorder._insert_event(
            event_type="run_created",
            status="created",
            payload={
                "watch_mode": task.watch_mode,
                "quantity": task.quantity,
                "profile_id": task.profile_id,
                "card_id": primary_card_id,
                "card_alias": primary_card_alias,
                "proxy": proxy,
            },
            ts=started_at,
        )
        return recorder

    async def record_status(
        self,
        status: str,
        *,
        step: str = "",
        payload: dict[str, Any] | None = None,
        ts: str | None = None,
    ) -> None:
        event_ts = ts or now_iso()
        await self._open_step(step, event_ts)
        await self._insert_event(
            event_type="status",
            status=status,
            step=step,
            payload=payload,
            ts=event_ts,
        )

    async def update_summary(self, **fields: Any) -> None:
        """Patch the current run summary with additional metadata discovered later."""
        allowed = {
            "task_name",
            "site",
            "sku",
            "profile_id",
            "card_id",
            "card_alias",
            "proxy",
            "watch_mode",
            "quantity",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        columns = ", ".join(f"{key}=?" for key in updates)
        values = list(updates.values()) + [self.run_id]
        await self._db.execute(f"UPDATE task_runs SET {columns} WHERE id=?", values)

    async def record_log(
        self,
        level: str,
        message: str,
        *,
        step: str = "",
        payload: dict[str, Any] | None = None,
        ts: str | None = None,
    ) -> None:
        event_ts = ts or now_iso()
        await self._open_step(step, event_ts)
        await self._insert_event(
            event_type="log",
            level=level,
            step=step,
            message=message,
            payload=payload,
            ts=event_ts,
        )

    async def finish(
        self,
        final_status: str,
        *,
        error_message: str = "",
        order_number: str = "",
        ts: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        finished_at = ts or now_iso()
        await self._close_step(finished_at, final_status)
        await self._db.execute(
            """UPDATE task_runs
               SET finished_at=?, duration_ms=?, final_status=?, order_number=?, error_message=?
               WHERE id=?""",
            (
                finished_at,
                _duration_ms(self.started_at, finished_at),
                final_status,
                order_number or None,
                error_message or None,
                self.run_id,
            ),
        )
        finish_payload = {
            "order_number": order_number or None,
            "error_message": error_message or None,
        }
        if payload:
            finish_payload.update(payload)
        await self._insert_event(
            event_type="run_finished",
            status=final_status,
            message=error_message or order_number,
            payload=finish_payload,
            ts=finished_at,
        )

    async def _open_step(self, step: str, ts: str) -> None:
        if not step or step == self._current_step:
            return
        await self._close_step(ts)
        cursor = await self._db.execute(
            "INSERT INTO task_run_steps (run_id, step, started_at) VALUES (?, ?, ?)",
            (self.run_id, step, ts),
        )
        self._current_step_row_id = cursor.lastrowid
        self._current_step = step
        self._current_step_started_at = ts

    async def _close_step(self, ts: str, terminal_status: str = "") -> None:
        if not self._current_step_row_id or not self._current_step_started_at:
            return
        await self._db.execute(
            """UPDATE task_run_steps
               SET finished_at=?, duration_ms=?, terminal_status=?
               WHERE id=?""",
            (
                ts,
                _duration_ms(self._current_step_started_at, ts),
                terminal_status or None,
                self._current_step_row_id,
            ),
        )
        self._current_step = ""
        self._current_step_started_at = ""
        self._current_step_row_id = None

    async def _insert_event(
        self,
        *,
        event_type: str,
        status: str = "",
        level: str = "",
        step: str = "",
        message: str = "",
        payload: dict[str, Any] | None = None,
        ts: str,
    ) -> None:
        self._event_seq += 1
        await self._db.execute(
            """INSERT INTO task_run_events
               (run_id, task_id, event_seq, event_type, status, level, step, message, payload, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.run_id,
                self.task_id,
                self._event_seq,
                event_type,
                status or None,
                level or None,
                step or None,
                message or None,
                _json(payload),
                ts,
            ),
        )
