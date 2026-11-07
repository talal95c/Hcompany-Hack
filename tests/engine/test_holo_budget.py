import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI

from engine.adapters.holo import HoloRequests, PacedHoloAdapter, retry_after
from engine.adapters.vision import HoloAssertVerifier
from engine.services.errors import AuthenticationError, InvalidResponse, ServiceTimeout
from engine.services.holo import HoloCloudClient
from tests.engine.test_servers import png


class Clock:
    def __init__(self):
        self.now = 0.0
        self.delays = []

    def __call__(self):
        return self.now

    async def sleep(self, delay):
        self.delays.append(delay)
        self.now += delay


def response(content):
    return {"id": "holo-test", "object": "chat.completion", "created": 1, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}]}


@pytest.mark.parametrize("operation", ["verify", "locate"])
@pytest.mark.parametrize("failure", ["quota", "timeout", "auth", "invalid", "exhausted"])
async def test_real_holo_transport_budget(operation, failure):
    seen, starts = [], []
    clock = Clock()

    def transport(request):
        seen.append(json.loads(request.content))
        starts.append(clock())
        if failure == "auth":
            return httpx.Response(401, json={"error": {"message": "denied"}})
        if failure == "invalid":
            return httpx.Response(200, json=response("not-json"))
        if len(seen) == 1 or failure == "exhausted":
            if failure == "quota":
                return httpx.Response(429, headers={"retry-after": "3"},
                                      json={"error": {"message": "quota"}})
            raise httpx.ReadTimeout("timeout", request=request)
        content = ('{"answer":"yes"}' if operation == "verify"
                   else '{"x":400,"y":500,"visible":true}')
        return httpx.Response(200, json=response(content))

    http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    raw = HoloCloudClient(client=AsyncOpenAI(api_key="test", http_client=http, max_retries=0))
    raw._desktop_requests = HoloRequests(raw, clock=clock, sleep=clock.sleep)
    adapter = PacedHoloAdapter(raw)
    verifier = HoloAssertVerifier(raw)
    assert verifier.client is adapter.requests
    try:
        async def call():
            if operation == "verify":
                return await verifier.verify(png(), "La valeur est 42", timeout_s=30)
            return await adapter.localize(png(), "Cellule A1", timeout_s=30)

        if failure in {"auth", "invalid", "exhausted"}:
            error = {"auth": AuthenticationError, "invalid": InvalidResponse,
                     "exhausted": ServiceTimeout}[failure]
            if failure == "invalid" and operation == "verify":
                assert (await call()).answer is None
            else:
                with pytest.raises(error):
                    await call()
            assert len(seen) == (3 if failure == "exhausted" else 1)
        else:
            result = await call()
            if operation == "verify":
                assert result.answer is True
            else:
                assert (result.x, result.y, result.target_visible) == (400, 500, True)
            assert len(seen) == 2
            assert starts == [0, 3 if failure == "quota" else 2]
        assert all(0 < body["max_tokens"] <= 32 for body in seen)
    finally:
        await raw.aclose()


async def test_timeout_is_per_attempt_and_cancel_does_not_retry():
    calls, limits = [], []

    async def complete(operation, timeout_s, **kwargs):
        limits.append(timeout_s)
        calls.append(operation)
        if len(calls) == 1:
            await asyncio.Event().wait()
        return "pass"

    clock = Clock()
    requests = HoloRequests(SimpleNamespace(_complete=complete), clock=clock, sleep=clock.sleep)
    assert await requests._complete("verify", 0.01) == "pass"
    assert len(calls) == 2
    assert all(limit <= 0.01 for limit in limits)
    calls.clear()
    task = asyncio.create_task(requests._complete("verify", 20))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) <= 1
    assert not requests.lock.locked()


async def test_verification_and_localization_serialize_and_pace():
    clock = Clock()
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def complete(operation, timeout_s, **kwargs):
        calls.append((operation, clock(), timeout_s))
        entered.set()
        await release.wait()
        return operation

    requests = HoloRequests(SimpleNamespace(_complete=complete), clock=clock, sleep=clock.sleep)
    first = asyncio.create_task(requests._complete("verify", 30))
    await entered.wait()
    second = asyncio.create_task(requests._complete("locate", 30))
    await asyncio.sleep(0)
    assert len(calls) == 1
    release.set()
    assert await asyncio.gather(first, second) == ["verify", "locate"]
    assert calls == [("verify", 0, 20), ("locate", 2, 20)]


@pytest.mark.parametrize("value,expected", [("2", 2), ("invalid", 0), ("-1", 0)])
def test_retry_after(value, expected):
    error = ServiceTimeout("holo", "failed")
    error.__cause__ = httpx.HTTPStatusError(
        "quota", request=httpx.Request("POST", "https://test.invalid"),
        response=httpx.Response(429, headers={"retry-after": value}))
    assert retry_after(error) == expected


def test_retry_after_http_date(monkeypatch):
    monkeypatch.setattr("engine.adapters.holo.time.time", lambda: 0)
    error = httpx.HTTPStatusError(
        "quota", request=httpx.Request("POST", "https://test.invalid"),
        response=httpx.Response(429, headers={"retry-after": "Thu, 01 Jan 1970 00:00:02 GMT"}))
    assert retry_after(error) == 2


async def test_retry_after_beyond_budget_does_not_issue_another_request():
    clock = Clock()
    calls = []

    async def complete(operation, timeout_s, **kwargs):
        calls.append(operation)
        error = ServiceTimeout("holo", "quota cooldown")
        error.__cause__ = httpx.HTTPStatusError(
            "quota", request=httpx.Request("POST", "https://test.invalid"),
            response=httpx.Response(429, headers={"retry-after": "120"}))
        raise error

    requests = HoloRequests(SimpleNamespace(_complete=complete), clock=clock, sleep=clock.sleep)
    with pytest.raises(ServiceTimeout, match="Budget"):
        await requests._complete("verify", 5)
    assert calls == ["verify"]
    assert clock.now == requests.budget_s(5)
