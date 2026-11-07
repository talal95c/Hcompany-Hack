"""Retry avec backoff exponentiel et jitter, réservé aux appels idempotents."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from engine.services.errors import QuotaExceeded, ServiceTimeout, ServiceUnavailable

T = TypeVar("T")
RETRYABLE: tuple[type[Exception], ...] = (ServiceUnavailable, QuotaExceeded, ServiceTimeout)


async def hedged(call: Callable[[], Awaitable[T]], threshold: float) -> T:
    tasks = {asyncio.create_task(call())}
    try:
        done, _ = await asyncio.wait(tasks, timeout=threshold)
        if done:
            return await next(iter(done))
        tasks.add(asyncio.create_task(call()))
        while tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    return task.result()
                except RETRYABLE:
                    if not pending:
                        raise
            tasks = pending
        raise AssertionError("unreachable")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def with_retry(
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.25,
    max_delay: float = 4.0,
    retry_on: tuple[type[Exception], ...] = RETRYABLE,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except retry_on as exc:
            if attempt == attempts:
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            await asyncio.sleep(
                max(min(max_delay, getattr(exc, "retry_after", 0)), delay * (0.5 + random.random()))
            )
    raise AssertionError("unreachable")


class TokenBucket:
    """Limiteur partagé (ex. 60 req/min Jev) : direct et spéculation puisent au même seau."""

    def __init__(self, rate_per_minute: float, capacity: int | None = None) -> None:
        self.rate = rate_per_minute / 60.0
        self.capacity = float(capacity or max(1, int(rate_per_minute)))
        self.tokens = self.capacity
        self._loop_time: float | None = None
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = asyncio.get_running_loop().time()
        if self._loop_time is not None:
            self.tokens = min(self.capacity, self.tokens + (now - self._loop_time) * self.rate)
        self._loop_time = now

    def try_acquire(self, reserve: float = 0.0) -> bool:
        """Prend un jeton sans attendre ; `reserve` garde des jetons pour les finals."""
        self._refill()
        if self.tokens - 1 >= reserve:
            self.tokens -= 1
            return True
        return False

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)
