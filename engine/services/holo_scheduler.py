"""Quota partagé, admission prioritaire et annulation des travaux devenus inutiles."""

import asyncio
import math
import os
import re
import time
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from email.utils import parsedate_to_datetime

_context = ContextVar("holo_request", default=(0, None))


class StaleSpeculation(asyncio.CancelledError):
    pass


@contextmanager
def speculative_request(current: Callable[[], bool]):
    _, previous = _context.get()
    token = _context.set((1, lambda: current() and (previous is None or previous())))
    try:
        yield
    finally:
        _context.reset(token)


def delay_seconds(value: str | None, *, reset: bool = False) -> float:
    if not value:
        return 0
    try:
        number = float(value)
        if reset and number > 1e9:
            number -= time.time()
        return max(0, number) if math.isfinite(number) else 0
    except ValueError:
        parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
        if parts and "".join(n + unit for n, unit in parts) == value:
            units = {"ms": .001, "s": 1, "m": 60, "h": 3600}
            return sum(float(n) * units[unit] for n, unit in parts)
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 0


class HoloScheduler:
    def __init__(self, *, requests: int | None = None, window_s: float | None = None,
                 concurrency: int = 4, clock=time.monotonic):
        self.requests = (int(os.getenv("ENGINE_HOLO_QUOTA_REQUESTS", "30"))
                         if requests is None else requests)
        self.window_s = (float(os.getenv("ENGINE_HOLO_QUOTA_WINDOW_S", "60"))
                         if window_s is None else window_s)
        if (self.requests < 1 or self.window_s <= 0 or not math.isfinite(self.window_s)
                or concurrency < 1):
            raise ValueError("Quota Holo invalide")
        self.limit = self.requests
        self.concurrency, self.clock = concurrency, clock
        self.starts = deque()
        self.condition = asyncio.Condition()
        self.pending = []
        self.sequence = 0
        self.active = 0
        self.blocked_until = 0.0
        self.remaining = None
        self.reset_at = 0.0

    async def observe(self, status: int, headers: Mapping[str, str]):
        headers = {k.lower(): v for k, v in headers.items()}
        def header(field):
            return (headers.get("x-ratelimit-" + field + "-requests")
                    or headers.get("x-ratelimit-" + field)
                    or headers.get("ratelimit-" + field))

        async with self.condition:
            now = self.clock()
            retry = delay_seconds(headers.get("retry-after"))
            if now >= self.reset_at:
                self.remaining = None
            try:
                limit = int(header("limit") or self.limit)
                if limit > 0:
                    self.limit = min(self.requests, limit)
                remaining = header("remaining")
                if remaining is not None:
                    value = max(0, int(remaining))
                    self.remaining = value if self.remaining is None else min(self.remaining, value)
                    self.reset_at = now + (delay_seconds(header("reset"), reset=True)
                                           or ((retry or 1) if status == 429 else self.window_s))
            except ValueError:
                pass
            if status == 429 or retry:
                self.blocked_until = max(self.blocked_until, now + (retry or 1))
            self.condition.notify_all()

    @asynccontextmanager
    async def slot(self):
        priority, current = _context.get()
        async with self.condition:
            self.sequence += 1
            ticket = (priority, self.sequence)
            self.pending.append(ticket)
            try:
                while True:
                    if current is not None and not current():
                        raise StaleSpeculation("Requête Holo obsolète")
                    now = self.clock()
                    while self.starts and self.starts[0] <= now - self.window_s:
                        self.starts.popleft()
                    if now >= self.reset_at:
                        self.remaining = None
                    if (ticket == min(self.pending) and self.active < self.concurrency
                            and len(self.starts) < self.limit and now >= self.blocked_until
                            and (self.remaining is None or self.remaining > 0)):
                        self.starts.append(now)
                        self.active += 1
                        if self.remaining is not None:
                            self.remaining -= 1
                        break
                    delays = [.05]
                    if len(self.starts) >= self.limit:
                        delays.append(max(.001, self.starts[0] + self.window_s - now))
                    try:
                        await asyncio.wait_for(self.condition.wait(), min(delays))
                    except TimeoutError:
                        pass
            finally:
                self.pending.remove(ticket)
                self.condition.notify_all()
        try:
            yield
        finally:
            async with self.condition:
                self.active -= 1
                self.condition.notify_all()

    async def run(self, factory):
        _, current = _context.get()
        async with self.slot():
            if current is None:
                return await factory()
            task = asyncio.create_task(factory())
            async def stale():
                while current():
                    await asyncio.sleep(.05)
                raise StaleSpeculation("Requête Holo obsolète")

            watcher = asyncio.create_task(stale())
            try:
                done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
                if watcher in done:
                    return await watcher
                return await task
            finally:
                task.cancel()
                watcher.cancel()
                await asyncio.gather(task, watcher, return_exceptions=True)
