"""Publication locale avec files bornées par abonné."""

import asyncio
import time
from collections import OrderedDict
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
        self.published_at: OrderedDict[str, float] = OrderedDict()
        self.subscribers: dict[Topic, list[asyncio.Queue[Any]]] = {}

    def subscribe(self, topic: Topic) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue(self.capacity)
        self.subscribers.setdefault(topic, []).append(queue)
        return queue

    def unsubscribe(self, topic: Topic, queue: asyncio.Queue[Any]) -> None:
        self.subscribers.get(topic, []).remove(queue)

    async def publish(self, topic: Topic, value: Any) -> None:
        if topic == Topic.COMMAND and isinstance(value, dict) and "command_id" in value:
            self.published_at[value["command_id"]] = time.perf_counter()
            if len(self.published_at) > self.capacity:
                self.published_at.popitem(last=False)
        for queue in tuple(self.subscribers.get(topic, [])):
            if topic == Topic.COMMAND:
                await queue.put(value)
                continue
            if queue.full():
                queue.get_nowait()
                queue.task_done()
                self.dropped += 1
                if self.report:
                    self.report({"kind": "queue_overflow", "topic": topic, "count": self.dropped})
            queue.put_nowait(value)