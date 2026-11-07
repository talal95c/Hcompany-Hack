from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import pytest

from bench.holo import Client
from bench.holo_pacing import Pacer, delay_seconds, rate_headers


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bench.holo_pacing.time.time", lambda: 1000000000)
    assert delay_seconds("2") == 2
    assert delay_seconds("1m2s") == 62
    assert delay_seconds("25ms") == 0.025
    assert delay_seconds("1000000003", epoch=True) == 3
    assert delay_seconds(format_datetime(datetime.fromtimestamp(1000000004, UTC))) == 4
    assert delay_seconds(None) == delay_seconds("invalid") == 0
    assert rate_headers(
        {"Retry-After": "3", "Authorization": "omitted", "X-RateLimit-Remaining-Requests": "0"}
    ) == {"retry-after": "3", "x-ratelimit-remaining-requests": "0"}


async def test_bucket_and_headers() -> None:
    clock = Clock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)
    assert await pacer.acquire() == {"pacing_wait_ms": 0, "cooldown_wait_ms": 0}
    assert (await pacer.acquire())["pacing_wait_ms"] == 2000
    pacer.observe(200, {"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "10s"}, 0)
    assert (await pacer.acquire())["cooldown_wait_ms"] == 10000
    pacer.observe(429, {"Retry-After": "45"}, 0)
    assert (await pacer.acquire())["cooldown_wait_ms"] == 45000
    assert pacer.interval == 3
    pacer.observe(429, {}, 19)
    assert (await pacer.acquire())["cooldown_wait_ms"] == 60000
    pacer.observe(200, {"ratelimit-remaining": "0", "ratelimit-reset": "7"}, 0)
    assert (await pacer.acquire())["cooldown_wait_ms"] == 7000
    pacer.observe(200, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "70"}, 0)
    assert (await pacer.acquire())["cooldown_wait_ms"] == 70000


async def test_retries_separate_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "unit-placeholder")
    client = Client()
    await client.http.aclose()
    clock = Clock()
    client.pacer = Pacer(clock=clock, sleep=clock.sleep)
    replies = iter(
        [
            httpx.Response(429, headers={"Retry-After": "30"}),
            httpx.Response(503),
            httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1, "y": 2}'}}]}),
            httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1, "y": 2}'}}]}),
        ]
    )
    client.http = httpx.AsyncClient(
        base_url="https://unit.invalid/", transport=httpx.MockTransport(lambda _: next(replies))
    )
    try:
        result = await client.call({})
        second = await client.call({})
    finally:
        await client.http.aclose()
    assert result["status"] == 200
    assert result["rate_limit_429_count"] == 1
    assert result["cooldown_wait_ms"] == 40000
    assert result["latency_ms"] == result["attempts"][-1]["latency_ms"]
    assert result["attempts"][0]["rate_headers"] == {"retry-after": "30"}
    assert second["pacing_wait_ms"] == 3000
    assert second["cooldown_wait_ms"] == 0
