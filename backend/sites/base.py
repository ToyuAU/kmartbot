"""
Abstract base class for all site bots.
Adding a new site (e.g. BigW) means subclassing BaseSite and implementing run().
"""

from abc import ABC, abstractmethod
from typing import Callable, Awaitable

from backend.models.task import Task
from backend.models.profile import Profile
from backend.models.card import Card


# Type for the structured log emitter injected by the task runner
LogFn = Callable[[str, str, str], Awaitable[None]]  # (level, message, step)


class BaseSite(ABC):
    """
    Interface every site bot must implement.

    The task runner instantiates the appropriate subclass based on task.site,
    then calls run(). The bot emits structured log events via self.log().
    """

    def __init__(self, task: Task, profile: Profile, card: Card, log_fn: LogFn):
        self.task = task
        self.profile = profile
        self.card = card
        self._log = log_fn

    async def log(self, level: str, message: str, step: str = "") -> None:
        await self._log(level, message, step)

    async def info(self, message: str, step: str = "") -> None:
        await self.log("info", message, step)

    async def warn(self, message: str, step: str = "") -> None:
        await self.log("warn", message, step)

    async def error(self, message: str, step: str = "") -> None:
        await self.log("error", message, step)

    async def success(self, message: str, step: str = "") -> None:
        await self.log("success", message, step)

    @abstractmethod
    async def run(self) -> str:
        """
        Execute the full checkout flow for this task.
        Returns the order number on success.
        Raises an exception on failure.
        """
        ...
