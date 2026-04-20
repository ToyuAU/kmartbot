"""
CRUD endpoints for tasks, plus start/stop controls.
Actual execution is delegated to core.task_manager.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List
import aiosqlite
from pydantic import BaseModel

from backend.database import get_db
from backend.models.task import Task, TaskCreate, TaskUpdate, TaskLog, TaskStatus
from backend.services.csv_utils import csv_text, parse_bool, parse_csv, split_pipe

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CsvImportBody(BaseModel):
    csv: str


def _resolve_unique(mapping: dict[str, list[str]], value: str, label: str, row_num: int) -> str:
    matches = mapping.get(value.strip(), [])
    if not matches:
        raise HTTPException(400, f'Invalid task row {row_num}: unknown {label} "{value}"')
    if len(matches) > 1:
        raise HTTPException(400, f'Invalid task row {row_num}: ambiguous {label} "{value}"')
    return matches[0]


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


@router.get("/export")
async def export_tasks_csv(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        """SELECT t.*, p.name AS profile_name
           FROM tasks t
           LEFT JOIN profiles p ON p.id = t.profile_id
           ORDER BY t.created_at DESC"""
    ) as cur:
        task_rows = await cur.fetchall()

    async with db.execute("SELECT id, alias FROM cards") as cur:
        card_rows = await cur.fetchall()
    card_alias_by_id = {row["id"]: row["alias"] for row in card_rows}

    fieldnames = [
        "name", "site", "sku", "profile_id", "profile_name",
        "card_ids", "card_aliases", "quantity",
        "use_staff_codes", "use_flybuys", "watch_mode",
    ]
    export_rows: list[dict[str, object]] = []
    for row in task_rows:
        task = Task.from_row(row)
        export_rows.append({
            "name": task.name,
            "site": task.site,
            "sku": task.sku,
            "profile_id": task.profile_id,
            "profile_name": row["profile_name"] or "",
            "card_ids": "|".join(task.card_ids),
            "card_aliases": "|".join(
                card_alias_by_id.get(card_id, "")
                for card_id in task.card_ids
                if card_alias_by_id.get(card_id)
            ),
            "quantity": task.quantity,
            "use_staff_codes": str(task.use_staff_codes).lower(),
            "use_flybuys": str(task.use_flybuys).lower(),
            "watch_mode": str(task.watch_mode).lower(),
        })

    payload = csv_text(export_rows, fieldnames)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tasks.csv"'},
    )


@router.post("/import", status_code=201)
async def import_tasks_csv(
    body: CsvImportBody,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = parse_csv(body.csv)

    async with db.execute("SELECT id, name FROM profiles") as cur:
        profile_rows = await cur.fetchall()
    async with db.execute("SELECT id, alias FROM cards") as cur:
        card_rows = await cur.fetchall()

    profile_ids = {row["id"] for row in profile_rows}
    card_ids = {row["id"] for row in card_rows}
    profile_name_map: dict[str, list[str]] = {}
    card_alias_map: dict[str, list[str]] = {}
    for row in profile_rows:
        profile_name_map.setdefault(row["name"], []).append(row["id"])
    for row in card_rows:
        card_alias_map.setdefault(row["alias"], []).append(row["id"])

    imported = 0
    for idx, row in enumerate(rows, start=2):
        profile_id = row.get("profile_id", "")
        profile_name = row.get("profile_name", "")
        if profile_id:
            if profile_id not in profile_ids:
                raise HTTPException(400, f'Invalid task row {idx}: unknown profile_id "{profile_id}"')
        elif profile_name:
            profile_id = _resolve_unique(profile_name_map, profile_name, "profile_name", idx)
        else:
            raise HTTPException(400, f'Invalid task row {idx}: "profile_id" or "profile_name" is required')

        resolved_card_ids: list[str] = []
        explicit_card_ids = split_pipe(row.get("card_ids", ""))
        if explicit_card_ids:
            unknown = [card_id for card_id in explicit_card_ids if card_id not in card_ids]
            if unknown:
                raise HTTPException(400, f'Invalid task row {idx}: unknown card_ids {", ".join(unknown)}')
            resolved_card_ids = explicit_card_ids
        else:
            for alias in split_pipe(row.get("card_aliases", "")):
                resolved_card_ids.append(_resolve_unique(card_alias_map, alias, "card_alias", idx))

        try:
            quantity_raw = row.get("quantity", "")
            task_in = TaskCreate(
                name=row.get("name", ""),
                site=row.get("site", "") or "kmart",
                sku=row.get("sku", ""),
                profile_id=profile_id,
                card_ids=resolved_card_ids,
                quantity=int(quantity_raw) if quantity_raw else 1,
                use_staff_codes=parse_bool(row.get("use_staff_codes", ""), default=True),
                use_flybuys=parse_bool(row.get("use_flybuys", ""), default=True),
                watch_mode=parse_bool(row.get("watch_mode", ""), default=False),
            )
        except ValueError as exc:
            raise HTTPException(400, f"Invalid task row {idx}: {exc}") from exc
        except Exception as exc:
            raise HTTPException(400, f"Invalid task row {idx}: {exc}") from exc

        if not task_in.sku:
            raise HTTPException(400, f'Invalid task row {idx}: "sku" is required')
        if task_in.quantity < 1:
            raise HTTPException(400, f'Invalid task row {idx}: "quantity" must be at least 1')

        now = Task.now()
        task = Task(
            id=Task.new_id(),
            created_at=now,
            updated_at=now,
            **task_in.model_dump(),
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
        imported += 1

    return {"imported": imported}


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
