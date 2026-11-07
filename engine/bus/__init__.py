"""Publication locale avec files bornées par abonné."""

import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Any


class Topic(StrEnum):
    EVENT = "event"
    CHECK = "check"
    DECISION = "decision"
    COMMAND = "command"
    DEBUG = "debug"


class EventBus:
    def __init__(self, capacity: int = 128, report: Callable[[dict], None] | None = None):
        if capacity < 1:
            raise ValueError("Capacité positive requise")
        self.capacity = capacity
        self.report = report
        self.dropped = 0
        self.subscribers: dict[Topic, list[asyncio.Queue[Any]]] = {}

    def subscribe(self, topic: Topic) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue(self.capacity)
        self.subscribers.setdefault(topic, []).append(queue)
        return queue

    def unsubscribe(self, topic: Topic, queue: asyncio.Queue[Any]) -> None:
        self.subscribers.get(topic, []).remove(queue)

    async def publish(self, topic: Topic, value: Any) -> None:
        for queue in tuple(self.subscribers.get(topic, [])):
            if queue.full():
                queue.get_nowait()
                queue.task_done()
                self.dropped += 1
                if self.report:
                    self.report({"kind": "queue_overflow", "topic": topic, "count": self.dropped})
            queue.put_nowait(value)