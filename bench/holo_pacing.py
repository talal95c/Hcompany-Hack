"""Single shared token bucket and server-directed cooldowns."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from email.utils import parsedate_to_datetime


def delay_seconds(value: str | None, *, epoch: bool = False) -> float:
    if not value:
        return 0
    try:
        number = float(value)
        return max(0, number - time.time() if epoch and number > 1e9 else number)
    except ValueError:
        pass
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
    if parts and "".join(n + unit for n, unit in parts) == value:
        return sum(float(n) * units[unit] for n, unit in parts)
    try:
        return max(0, parsedate_to_datetime(value).timestamp() - time.time())
    except (ValueError, TypeError, OverflowError):
        return 0


def rate_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in headers.items()
        if "ratelimit" in k.lower().replace("-", "") or k.lower() == "retry-after"
    }


class Pacer:
    def __init__(
        self,
        interval: float = 2,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.tokens = 1.0
        self.updated = clock()
        self.blocked_until = 0.0

    async def acquire(self) -> dict[str, float]:
        waits = {"pacing_wait_ms": 0.0, "cooldown_wait_ms": 0.0}
        while True:
            now = self.clock()
            self.tokens = min(1.0, self.tokens + (now - self.updated) / self.interval)
            self.updated = now
            cooldown = max(0, self.blocked_until - now)
            pacing = max(0, (1 - self.tokens) * self.interval)
            delay = max(cooldown, pacing)
            if delay <= 1e-6:
                self.tokens = max(0, self.tokens - 1)
                return waits
            started = self.clock()
            await self.sleep(delay)
            key = "cooldown_wait_ms" if cooldown >= pacing else "pacing_wait_ms"
            waits[key] += (self.clock() - started) * 1000

    def observe(self, status: int, headers: Mapping[str, str], retry: int) -> None:
        headers = {k.lower(): v for k, v in headers.items()}
        delay = delay_seconds(headers.get("retry-after"))
        for prefix in ("ratelimit", "x-ratelimit"):
            try:
                if float(headers.get(f"{prefix}-remaining", "1")) <= 0:
                    delay = max(
                        delay, delay_seconds(headers.get(f"{prefix}-reset"), epoch=True)
                    )
            except ValueError:
                pass
        for resource in ("requests", "tokens"):
            remaining = headers.get(f"x-ratelimit-remaining-{resource}")
            reset = delay_seconds(headers.get(f"x-ratelimit-reset-{resource}"), epoch=True)
            try:
                if remaining is not None and float(remaining) <= 0:
                    delay = max(delay, reset)
                if resource == "requests" and remaining is not None and float(remaining) > 0:
                    self.interval = max(self.interval, reset / float(remaining))
            except ValueError:
                pass
        if status == 429:
            self.interval = min(60, max(self.interval * 1.5, 2))
            delay = max(delay, min(60, 15 * 2 ** min(retry, 2)))
        elif status >= 500 or status == 0:
            delay = max(delay, min(60, 5 * 2 ** min(retry, 4)))
        self.blocked_until = max(self.blocked_until, self.clock() + delay)
