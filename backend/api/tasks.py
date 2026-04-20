"""
CRUD endpoints for tasks, plus start/stop controls.
Actual execution is delegated to core.task_manager.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from backend.database import get_db
from backend.models.task import Task, TaskCreate, TaskUpdate, TaskLog, TaskStatus

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── Bulk controls (must be defined before /{task_id} routes) ─────────────────

@router.post("/start-all", status_code=200)
async def start_all_tasks(db: aiosqlite.Connection = Depends(get_db)):
    """Start every idle/failed/stopped task."""
    async with db.execute(
        "SELECT id FROM tasks WHERE status IN ('idle', 'failed', 'stopped')"
    ) as cur:
        rows = await cur.fetchall()
    from backend.core.task_manager import task_manager
    for row in rows:
        await task_manager.start(row["id"])
    return {"started": len(rows)}


@router.post("/stop-all", status_code=200)
async def stop_all_tasks():
    """Stop every running task."""
    from backend.core.task_manager import task_manager
    await task_manager.stop_all()
    return {"ok": True}


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[Task])
async def list_tasks(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM tasks ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    return [Task.from_row(r) for r in rows]


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    return Task.from_row(row)


@router.post("", response_model=Task, status_code=201)
async def create_task(body: TaskCreate, db: aiosqlite.Connection = Depends(get_db)):
    now = Task.now()
    task = Task(
        id=Task.new_id(),
        created_at=now,
        updated_at=now,
        **body.model_dump(),
    )
    await db.execute(
        """INSERT INTO tasks
           (id, name, site, sku, profile_id, card_ids, quantity,
            use_staff_codes, use_flybuys, watch_mode, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task.id, task.name, task.site, task.sku, task.profile_id,
         json.dumps(task.card_ids), task.quantity,
         int(task.use_staff_codes), int(task.use_flybuys), int(task.watch_mode),
         task.status, task.created_at, task.updated_at),
    )
    return task


@router.patch("/{task_id}", response_model=Task)
async def update_task(
    task_id: str, body: TaskUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Task not found")

    existing = Task.from_row(row)
    updates = body.model_dump(exclude_none=True)
    updated = existing.model_copy(update={**updates, "updated_at": Task.now()})

    await db.execute(
        """UPDATE tasks SET name=?, sku=?, profile_id=?, card_ids=?, quantity=?,
           use_staff_codes=?, use_flybuys=?, watch_mode=?, updated_at=? WHERE id=?""",
        (updated.name, updated.sku, updated.profile_id, json.dumps(updated.card_ids),
         updated.quantity, int(updated.use_staff_codes), int(updated.use_flybuys),
         int(updated.watch_mode), updated.updated_at, task_id),
    )
    return updated


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: aiosqlite.Connection = Depends(get_db)):
    # Stop it first if running
    from backend.core.task_manager import task_manager
    await task_manager.stop(task_id)
    await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


# ── Control ───────────────────────────────────────────────────────────────────

@router.post("/{task_id}/start", response_model=Task)
async def start_task(task_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Task not found")

    task = Task.from_row(row)
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(409, "Task is already running")

    from backend.core.task_manager import task_manager
    await task_manager.start(task_id)

    task.status = TaskStatus.RUNNING
    return task


@router.post("/{task_id}/stop", response_model=Task)
async def stop_task(task_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Task not found")

    from backend.core.task_manager import task_manager
    await task_manager.stop(task_id)

    task = Task.from_row(row)
    task.status = TaskStatus.STOPPED
    return task


# ── Logs ──────────────────────────────────────────────────────────────────────

@router.get("/{task_id}/logs", response_model=List[TaskLog])
async def get_task_logs(
    task_id: str,
    limit: int = 200,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT * FROM task_logs WHERE task_id = ? ORDER BY id DESC LIMIT ?",
        (task_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    # Return in chronological order
    return [TaskLog.from_row(r) for r in reversed(rows)]
