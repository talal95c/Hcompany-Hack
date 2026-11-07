"""Budget partagé de requêtes Holo : une requête en vol, pacing et retries bornés."""

import asyncio
import json
import math
import time
from email.utils import parsedate_to_datetime

from engine.interfaces import LocalizeResult
from engine.services.errors import (
    InvalidResponse,
    QuotaExceeded,
    ServiceTimeout,
    ServiceUnavailable,
)


def retry_after(error: Exception) -> float:
    cause = error
    while cause is not None:
        response = getattr(cause, "response", None)
        if response is not None:
            value = response.headers.get("retry-after", "")
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = parsedate_to_datetime(value).timestamp() - time.time()
                except (ValueError, TypeError, OverflowError):
                    return 0
            return max(0, delay) if math.isfinite(delay) else 0
        cause = cause.__cause__
    return 0


class HoloRequests:
    def __init__(self, client, *, interval_s: float = 2, attempts: int = 3,
                 clock=time.monotonic, sleep=asyncio.sleep):
        self.client = client
        self.interval_s, self.attempts = interval_s, attempts
        self.clock, self.sleep = clock, sleep
        self.lock = asyncio.Lock()
        self.next_request = 0.0

    def budget_s(self, timeout_s: float) -> float:
        return self.attempts * min(timeout_s, 20) + 10

    async def _complete(self, operation: str, timeout_s: float, **kwargs):
        deadline = self.clock() + self.budget_s(timeout_s)
        async with asyncio.timeout(self.budget_s(timeout_s)):
            async with self.lock:
                for attempt in range(self.attempts):
                    wait = max(0, self.next_request - self.clock())
                    if wait:
                        await self.sleep(min(wait, max(0, deadline - self.clock())))
                    if self.clock() >= deadline:
                        raise ServiceTimeout("holo", "Budget épuisé avant le prochain essai")
                    limit = min(timeout_s, 20, deadline - self.clock())
                    self.next_request = self.clock() + self.interval_s
                    try:
                        return await asyncio.wait_for(
                            self.client._complete(operation, limit, **kwargs), limit)
                    except (ServiceTimeout, ServiceUnavailable, QuotaExceeded,
                            TimeoutError) as error:
                        delay = max(retry_after(error), min(8, 2 ** (attempt + 1)))
                        self.next_request = max(self.next_request, self.clock() + delay)
                        if attempt + 1 == self.attempts:
                            raise
        raise AssertionError("Budget Holo vide")


def shared_requests(client) -> HoloRequests:
    if isinstance(client, HoloRequests):
        return client
    requests = getattr(client, "_desktop_requests", None)
    if requests is None:
        requests = HoloRequests(client)
        client._desktop_requests = requests
    return requests


def localization_budget(holo, timeout_s: float) -> float:
    return holo.budget_s(timeout_s) if isinstance(holo, PacedHoloAdapter) else timeout_s


class PacedHoloAdapter:
    def __init__(self, client):
        self.client = client
        self.requests = shared_requests(client)

    def budget_s(self, timeout_s: float) -> float:
        return self.requests.budget_s(timeout_s)

    async def localize(self, image_png: bytes, description: str, *, timeout_s: float):
        from engine.services.holo import (
            _POINT_SCHEMA,
            LOCATE_SYSTEM_PROMPT,
            _check_point,
            _confidence,
            _png_data_url,
        )

        if not description.strip():
            raise ValueError("Description vide")
        start = time.perf_counter()
        response = await self.requests._complete(
            "locate", timeout_s,
            messages=[{"role": "system", "content": LOCATE_SYSTEM_PROMPT},
                      {"role": "user", "content": [
                          {"type": "image_url", "image_url": {"url": _png_data_url(image_png)}},
                          {"type": "text", "text": description.strip()}]}],
            max_tokens=32, logprobs=True,
            response_format={"type": "json_schema", "json_schema": {
                "name": "point", "schema": _POINT_SCHEMA, "strict": True}},
        )
        choice = response.choices[0]
        try:
            point = json.loads(choice.message.content or "")
            if not isinstance(point, dict):
                raise ValueError
        except (ValueError, TypeError) as error:
            raise InvalidResponse("holo", "Point illisible") from error
        x, y = _check_point(point.get("x"), point.get("y"), response.id)
        confidence = _confidence(choice)
        return LocalizeResult(round(x), round(y),
                              confidence if math.isfinite(confidence) else None,
                              (time.perf_counter() - start) * 1000, point.get("visible"))

    async def aclose(self):
        await self.client.aclose()
