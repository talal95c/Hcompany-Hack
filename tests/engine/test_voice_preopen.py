import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from engine.interfaces import JevDecision
from engine.lesson.live_audio import LiveUtterance
from engine.lesson.voice import IntentSpeculation, PreopenedSession
from engine.services.errors import QuotaExceeded
from engine.services.gladia import GladiaLiveSession, GladiaSttClient
from engine.services.latency import LatencyRecorder

from . import test_servers
from .test_pointer_streaming import Session
from .test_policy import help_context, setup

runtime = test_servers.runtime

CONFIG = dict(sample_rate=16000, language="fr", endpointing_s=.05, vocabulary=())


class Client:
    def __init__(self):
        self.sessions = []

    async def open_live(self, **config):
        session = Session()
        self.sessions.append(session)
        return session


async def ready(pool):
    async with asyncio.timeout(1):
        while not pool.pending:
            await asyncio.sleep(0)
        await pool.pending


async def test_preopen_reuses_single_spare_without_audio_and_closes():
    client = Client()
    pool = PreopenedSession(client, interval_s=0)
    pool.warm(**CONFIG)
    assert pool.pending is None
    pool.enabled = True
    for _ in range(10):
        pool.warm(**CONFIG)
    await ready(pool)
    assert len(client.sessions) == 1 and client.sessions[0].audio == []
    session = await pool.acquire(**CONFIG)
    assert session is client.sessions[0] and pool.spare is None
    pool.warm(**CONFIG)
    assert len(client.sessions) == 1
    await session.aclose()
    pool.release()
    await ready(pool)
    assert len(client.sessions) == 2
    await pool.close()
    assert all(s.closed for s in client.sessions)


async def test_spare_rotates_at_expiry_and_replaces_remote_closed_or_wrong_format():
    client = Client()
    pool = PreopenedSession(client, ttl_s=.02, interval_s=0)
    pool.enabled = True
    pool.warm(**CONFIG)
    await ready(pool)
    async with asyncio.timeout(1):
        while len(client.sessions) < 2:
            await asyncio.sleep(0)
    await ready(pool)
    assert client.sessions[0].closed
    pool.spare.closed = True
    taken = await pool.acquire(**{**CONFIG, "sample_rate": 48000})
    assert taken is client.sessions[-1] and len(client.sessions) == 3
    await taken.aclose()
    pool.release()
    await pool.close()
    assert all(s.closed for s in client.sessions)


async def test_revoke_while_opening_cancels_init_and_leaves_no_session():
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def open_live(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    pool = PreopenedSession(SimpleNamespace(open_live=open_live))
    pool.enabled = True
    pool.warm(**CONFIG)
    await started.wait()
    await pool.close()
    assert cancelled.is_set() and pool.spare is None and not pool.enabled


async def test_quota_failure_backs_off_without_repeated_requests():
    calls = []

    async def open_live(**kwargs):
        calls.append(True)
        raise QuotaExceeded("gladia", "quota", retry_after=60)

    pool = PreopenedSession(SimpleNamespace(open_live=open_live), interval_s=0)
    pool.enabled = True
    pool.warm(**CONFIG)
    await ready(pool)
    assert pool.next_open - time.monotonic() > 59
    pool.warm(**CONFIG)
    await asyncio.sleep(0)
    await pool.close()
    assert calls == [True]


async def test_runtime_mic_consent_ptt_revoke_and_mute(runtime):
    client = Client()
    runtime.stt = client
    runtime.voice_pool = PreopenedSession(client, interval_s=0)
    runtime.prepare_voice()
    assert not client.sessions
    permissions = {"screen": False, "accessibility": False, "microphone": True}
    await runtime.desktop_message({"type": "permissions", "payload": permissions}, None)
    await ready(runtime.voice_pool)
    assert client.sessions[0].audio == []
    await runtime.audio_message("ptt.start", {"utterance_id": "u"}, None)
    await runtime.desktop_message({"type": "permissions", "payload": {
        **permissions, "microphone": False}}, None)
    assert client.sessions[0].closed and not runtime.utterances
    await runtime.desktop_message({"type": "permissions", "payload": permissions}, None)
    await ready(runtime.voice_pool)
    await runtime.policy.intent("chut")
    async with asyncio.timeout(1):
        while not all(s.closed for s in client.sessions):
            await asyncio.sleep(0)
    assert not runtime.voice_pool.enabled


async def test_borrowed_session_only_sends_after_ptt_audio_feed():
    client = Client()
    pool = PreopenedSession(client, interval_s=0)
    pool.enabled = True
    pool.warm(**CONFIG)
    await ready(pool)

    async def callback(*args):
        pass

    stream = LiveUtterance(client, 16000, callback, callback, pool=pool)
    await asyncio.sleep(0)
    assert client.sessions[0].audio == []
    stream.feed(0, b"\0\0")
    stream.stop()
    await stream.task
    await pool.close()
    assert client.sessions[0].audio == [b"\0\0"]


async def test_revoked_consent_never_sends_queued_audio_even_if_open_completed():
    client = Client()

    async def callback(*args):
        pass

    stream = LiveUtterance(client, 16000, callback, callback, allowed=lambda: False)
    stream.feed(0, b"\0\0")
    await asyncio.gather(stream.task, return_exceptions=True)
    assert client.sessions[0].audio == [] and client.sessions[0].closed


async def test_runtime_stop_closes_spare(runtime):
    client = Client()
    runtime.voice_pool = PreopenedSession(client, interval_s=0)
    runtime.permissions["microphone"] = True
    runtime.prepare_voice()
    await ready(runtime.voice_pool)
    await runtime.close()
    assert all(s.closed for s in client.sessions)
    assert not runtime.voice_pool.enabled


async def test_explicit_ptt_can_listen_for_resume_while_tutor_muted(runtime):
    runtime.voice_pool = PreopenedSession(Client(), interval_s=0)
    runtime.permissions["microphone"] = True
    runtime.policy.muted = True
    await runtime.audio_message("ptt.start", {"utterance_id": "resume"}, None)
    runtime.prepare_voice()
    await ready(runtime.voice_pool)
    assert runtime.voice_pool.enabled and "resume" in runtime.utterances
    await runtime.close_audio()


async def test_partial_stability_timer_and_classification_error_fall_back():
    started = asyncio.Event()

    async def classify(text):
        started.set()
        raise RuntimeError("service unavailable")

    spec = IntentSpeculation(classify, lambda: True, generation=0, stable_s=.01)
    spec.partial("pourquoi")
    assert not started.is_set()
    await asyncio.wait_for(started.wait(), 1)
    assert await spec.final("pourquoi") is None
    await spec.close()


async def test_stable_partial_hit_speech_end_and_no_actions_before_final():
    calls = []
    answer = JevDecision("question", None, 0)

    async def classify(text):
        calls.append(text)
        return answer

    spec = IntentSpeculation(classify, lambda: True, generation=4, stable_s=.01)
    spec.partial(" Pourquoi un tore ? ")
    spec.partial(" Pourquoi un tore ? ")
    assert not calls
    spec.speech_end()
    await asyncio.sleep(0)
    result = await spec.final("pourquoi un tore?")
    assert result == ("pourquoi un tore", 4, answer)
    assert calls == ["pourquoi un tore"]
    await spec.close()


async def test_speculation_miss_cancels_request_and_stale_generation_never_reuses():
    started, cancelled = asyncio.Event(), asyncio.Event()
    current = True

    async def classify(text):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    spec = IntentSpeculation(classify, lambda: current, generation=0, stable_s=0)
    spec.partial("pourquoi")
    await started.wait()
    assert await spec.final("ne fais rien") is None
    assert cancelled.is_set()
    current = False
    spec.partial("pourquoi")
    assert await spec.final("pourquoi") is None
    await spec.close()


async def test_final_before_stability_does_not_wait_and_empty_partial_cancels():
    calls = []

    async def classify(text):
        calls.append(text)

    spec = IntentSpeculation(classify, lambda: True, generation=0, stable_s=30)
    spec.partial("incomplet")
    spec.partial("")
    assert await spec.final("autre") is None
    assert calls == []


@pytest.mark.parametrize("text,generation,hit", [("pourquoi", 1, True),
    ("ne fais rien", 1, False), ("pourquoi", 2, False)])
async def test_policy_rechecks_prediction_text_and_generation(text, generation, hit):
    class Jev:
        calls = 0

        async def decide(self, *args, **kwargs):
            self.calls += 1
            return JevDecision("other", None, 0)

    jev = Jev()
    policy, _, _, _, _ = setup(jev=jev)
    result = await policy.intent(text, help_context(), prediction=("pourquoi", generation,
        JevDecision("question", None, 0)))
    assert bool(result) is hit
    assert jev.calls == (0 if hit else 1)


def test_voice_configuration_rejects_invalid_delays():
    from engine.config import EngineConfig

    for value in (0, -1, float("nan"), 100):
        with pytest.raises(ValueError):
            replace(EngineConfig(), voice_preopen_ttl_s=value)


async def test_gladia_close_survives_cancellation_and_stops_without_audio():
    started, finish = asyncio.Event(), asyncio.Event()

    class Socket:
        closed = False
        sent = []

        async def __aiter__(self):
            await asyncio.Event().wait()
            yield ""

        async def send(self, data):
            self.sent.append(data)

        async def close(self):
            started.set()
            await finish.wait()
            self.closed = True

    socket = Socket()
    session = GladiaLiveSession(socket, "test", LatencyRecorder())
    closing = asyncio.create_task(session.aclose())
    await started.wait()
    closing.cancel()
    finish.set()
    await asyncio.gather(closing, return_exceptions=True)
    await session.aclose()
    assert socket.closed and session.closed
    assert socket.sent == ['{"type": "stop_recording"}']


async def test_gladia_quota_retry_after_reaches_preopen_backoff():
    async with GladiaSttClient(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(429, headers={"Retry-After": "61"}),
    )) as client:
        with pytest.raises(QuotaExceeded) as error:
            await client.open_live()
        assert error.value.retry_after == 61
