"""Caches LRU bornés et préchargement annulable sans action native."""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from engine.interfaces import LocalizeResult

T = TypeVar("T")


class LRU(Generic[T]):
    def __init__(self, capacity: int = 128):
        if capacity < 1:
            raise ValueError("Capacité positive requise")
        self.capacity = capacity
        self.entries: OrderedDict[object, T] = OrderedDict()

    def put(self, key: object, value: T) -> None:
        self.entries[key] = value
        self.entries.move_to_end(key)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)

    def get(self, key: object) -> T | None:
        if key not in self.entries:
            return None
        self.entries.move_to_end(key)
        return self.entries[key]


@dataclass(frozen=True)
class TargetContext:
    blender_version: str
    region_size: tuple[int, int]
    ui_scale: float
    target: str
    origin: tuple[int, int]
    monitor_id: str
    language: str
    ui_revision: int
    visible: bool
    menu_context: str = ""

    @property
    def key(self) -> tuple:
        return self.blender_version, self.region_size, self.ui_scale, self.target


@dataclass(frozen=True)
class TargetEntry:
    context: TargetContext
    result: LocalizeResult
    capture_id: str


class TargetCache(LRU[TargetEntry]):
    def put_target(self, entry: TargetEntry) -> None:
        self.put(entry.context.key, entry)

    def get(self, context: TargetContext) -> TargetEntry | None:
        entry = super().get(context.key)
        return entry if entry and context.visible and entry.context == context else None

    def get_target(self, context: TargetContext) -> TargetEntry | None:
        return self.get(context)

    def invalidate(self) -> None:
        self.entries.clear()

    def on_event(self, event: dict) -> None:
        if event["type"] in {"regions.changed", "menu.changed", "context.changed"}:
            self.invalidate()


@dataclass(frozen=True)
class AudioEntry:
    data: bytes | None = None
    audio_ref: str | None = None


class AudioCache(LRU[AudioEntry]):
    pass


class Preloader:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self.generation = -1

    async def cancel(self) -> None:
        self.generation += 1
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def start(
        self, generation: int, context: TargetContext, capture_id: str,
        localize: Callable[[], Awaitable[LocalizeResult | None]], cache: TargetCache,
        *, timeout_s: float = 5,
    ) -> None:
        await self.cancel()
        self.generation = generation

        async def run() -> None:
            try:
                result = await asyncio.wait_for(localize(), timeout_s)
                if result is not None and self.generation == generation:
                    cache.put_target(TargetEntry(context, result, capture_id))
            except Exception:
                return

        self.task = asyncio.create_task(run())