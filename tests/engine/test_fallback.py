import asyncio

import pytest

from engine.fallback import Fallback, with_fallback
from engine.interfaces import FakeClock, Transcript


async def test_generic_success_error_timeout():
    async def value():
        return 42

    async def error():
        raise ValueError("indisponible")

    assert await with_fallback(value(), 1, lambda: 0) == 42
    assert await with_fallback(error(), 1, lambda: 0) == 0
    assert await with_fallback(asyncio.sleep(1), 0.001, lambda: "clavier") == "clavier"


async def test_health_backoff_metrics_and_recovery():
    clock, metrics = FakeClock(), []
    fallback = Fallback(clock, metrics.append)
    calls = 0

    async def error():
        nonlocal calls
        calls += 1
        raise RuntimeError

    assert await fallback.call("jev", error, 1, lambda: "local") == "local"
    assert await fallback.call("jev", error, 1, lambda: "local") == "local"
    assert calls == 1
    assert fallback.health["jev"].consecutive_failures == 1
    assert [m["status"] for m in metrics] == ["fallback", "backoff"]
    clock.advance(1)

    async def ok():
        return "intervene"

    assert await fallback.call("jev", ok, 1, lambda: None) == "intervene"
    assert fallback.health["jev"].consecutive_failures == 0
    assert all(m["latency_ms"] >= 0 for m in metrics)
    assert Fallback().health == {}


async def test_cancellation_propagates():
    metrics = []
    fallback = Fallback(record=metrics.append)
    started = asyncio.Event()

    async def block():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(fallback.call("holo", block, 5, lambda: None))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert metrics[-1]["status"] == "cancelled"
    assert fallback.health["holo"].consecutive_failures == 0


@pytest.mark.parametrize("mode", ["ok", "missing", "empty", "error", "timeout"])
async def test_stt_and_tts_rules(mode):
    class Voice:
        async def transcribe(self, *args, **kwargs):
            if mode == "timeout":
                await asyncio.sleep(1)
            if mode == "error":
                raise OSError
            return Transcript("bonjour" if mode == "ok" else "", 0)

        async def synthesize(self, *args, **kwargs):
            if mode == "timeout":
                await asyncio.sleep(1)
            if mode == "error":
                raise OSError
            return b"audio" if mode == "ok" else b""

    events = []
    fallback = Fallback(record=events.append)
    client = None if mode == "missing" else Voice()
    transcript = await fallback.transcribe(
        client, b"audio", encoding="pcm", sample_rate=16000, language="fr", timeout=0.001,
    )
    audio = await fallback.synthesize(client, "bonjour", language="fr", timeout=0.001)
    if mode == "ok":
        assert transcript.text == "bonjour" and audio == b"audio"
    else:
        assert transcript is None and audio is None
        assert any(e.get("code") == "stt_unavailable" and e["retryable"] for e in events)
    assert len([e for e in events if e["kind"] == "latency"]) == 2
