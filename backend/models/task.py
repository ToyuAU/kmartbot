"""Task model — represents one checkout attempt for a single SKU."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel


class TaskStatus:
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STOPPED = "stopped"


class TaskCreate(BaseModel):
    name: str = ""
    site: str = "kmart"
    sku: str
    profile_id: str
    card_ids: List[str] = []
    quantity: int = 1
    use_staff_codes: bool = True
    use_flybuys: bool = True
    watch_mode: bool = False


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    profile_id: Optional[str] = None
    card_ids: Optional[List[str]] = None
    quantity: Optional[int] = None
    use_staff_codes: Optional[bool] = None
    use_flybuys: Optional[bool] = None
    watch_mode: Optional[bool] = None


class Task(TaskCreate):
    id: str
    status: str = TaskStatus.IDLE
    error_message: Optional[str] = None
    order_number: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "Task":
        d = dict(row)
        d["card_ids"] = json.loads(d.get("card_ids") or "[]")
        d["watch_mode"] = bool(d.get("watch_mode") or 0)
        return cls(**d)

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


class TaskLog(BaseModel):
    id: Optional[int] = None
    task_id: str
    level: str  # info | warn | error | success
    message: str
    step: str = ""
    ts: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "TaskLog":
        return cls(**dict(row))
