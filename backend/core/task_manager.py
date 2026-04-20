"""
Task manager — owns the registry of running asyncio.Task handles.
Provides start / stop / stop_all operations.
Imported as a singleton: `from backend.core.task_manager import task_manager`
"""

import asyncio
from typing import Optional


class TaskManager:
    def __init__(self):
        # task_id → asyncio.Task
        self._running: dict[str, asyncio.Task] = {}

    async def start(self, task_id: str) -> None:
        """Launch a new asyncio.Task for task_id. No-ops if already running."""
        if task_id in self._running and not self._running[task_id].done():
            return
        from backend.core.task_runner import run_task
        t = asyncio.create_task(run_task(task_id), name=f"task-{task_id}")
        self._running[task_id] = t
        # Auto-cleanup the handle when done
        t.add_done_callback(lambda _: self._running.pop(task_id, None))

    async def stop(self, task_id: str) -> None:
        """Cancel a running task. No-ops if not running."""
        t = self._running.get(task_id)
        if t and not t.done():
            t.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(t), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def stop_all(self) -> None:
        """Cancel all running tasks."""
        ids = list(self._running.keys())
        await asyncio.gather(*[self.stop(tid) for tid in ids], return_exceptions=True)

    def is_running(self, task_id: str) -> bool:
        t = self._running.get(task_id)
        return t is not None and not t.done()

    def running_count(self) -> int:
        return sum(1 for t in self._running.values() if not t.done())


# Singleton
task_manager = TaskManager()
