import asyncio
import json
from pathlib import Path

import pytest

from engine.config import EngineConfig
from engine.services._retry import hedged, with_retry
from engine.services.adapters import build_clients
from engine.services.errors import QuotaExceeded, ServiceTimeout
from engine.services.profiles import profile_for_lesson


async def test_retry_after(monkeypatch):
    delays = []
    calls = 0

    async def sleep(delay):
        delays.append(delay)

    async def call():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise QuotaExceeded("test", "quota", retry_after=2)
        return 42

    monkeypatch.setattr(asyncio, "sleep", sleep)
    assert await with_retry(call) == 42
    assert delays == [2]


async def test_hedge_wins_and_cancels_hang():
    calls = 0
    cancelled = asyncio.Event()

    async def call():
        nonlocal calls
        calls += 1
        if calls == 1:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return 42

    assert await hedged(call, 0.01) == 42
    assert cancelled.is_set()


async def test_budget_exhaustion():
    from types import SimpleNamespace

    from engine.services.holo import HoloCloudClient

    async def create(**kwargs):
        await asyncio.Event().wait()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    holo = HoloCloudClient(client=client)
    with pytest.raises(ServiceTimeout, match="budget exhausted"):
        await holo._complete("verify", 0.15)


def test_lesson_profiles(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    lesson = root / "lessons/donut/lesson.json"
    assert profile_for_lesson(json.loads(lesson.read_text())).id == "blender"
    assert profile_for_lesson({"app": {"id": "excel"}}).id == "excel"
    assert profile_for_lesson({"app": {"id": "missing"}}).id == "generic"
    monkeypatch.setenv("CODIV_API_KEY", "test")
    monkeypatch.setenv("GLADIA_API_KEY", "test")
    monkeypatch.setenv("LINKUP_API_KEY", "test")
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    clients = build_clients(EngineConfig(lesson=lesson))
    assert "docs.blender.org" in clients["search"].profile.docs_domains
    assert "Blender" in clients["jev"].profile.jev_context
    assert clients["stt"].profile.vocabulary


async def test_loop_survives_transient():
    from engine.services.computer_use import run_steps
    from engine.services.protocols import HoloAction

    class Holo:
        calls = 0

        async def act(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ServiceTimeout("holo", "transient")
            return HoloAction(type="done")

    async def capture():
        return b"image"

    async def execute(action):
        return "ok"

    result = await run_steps(Holo(), "goal", capture=capture, execute=execute)
    assert result.status == "success"
