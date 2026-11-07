# ruff: noqa: E402

import asyncio
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest

httpx = pytest.importorskip(
    "httpx", reason="Installez les dépendances : pip install -e '.[engine]'",
)
pytest.importorskip("websockets", reason="Installez les dépendances : pip install -e '.[engine]'")

from live_clients import (
    CodivClient,
    GladiaHttpClient,
    HoloHttpClient,
    LinkupHttpClient,
    menu_png,
    spoken_wav,
)

from engine.bus import EventBus, Topic
from engine.checks import SceneState, evaluate
from engine.config import EngineConfig
from engine.fallback import Fallback
from engine.interfaces import (
    FakeClock,
    HoloClient,
    JevClient,
    LocalizeResult,
    SearchClient,
    SttClient,
    Transcript,
)
from engine.lesson import load_lesson
from engine.policy import HelpPolicy

pytestmark = pytest.mark.live


def key(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"Variable {name} absente")
    return value


def show(service: str, metrics: list[dict]) -> dict:
    metric = next(m for m in reversed(metrics) if m.get("service") == service)
    print(f"LIVE {service}: status={metric['status']} latency_ms={metric['latency_ms']:.2f}")
    return metric


async def test_live_jev_policy_ambiguity():
    metrics = []
    clock, bus = FakeClock(), EventBus()
    fallback = Fallback(clock, metrics.append)
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + key("CODIV_API_KEY")},
                                 timeout=20) as http:
        client = CodivClient(http)
        assert isinstance(client, JevClient)
        models = await fallback.call("codiv.models", client.discover, 20, lambda: [])
        assert models
        show("codiv.models", metrics)
        root = Path(__file__).resolve().parent
        step = load_lesson(root / "fixtures/donut_lesson.json")["steps"][0]
        policy = HelpPolicy(EngineConfig(), bus, clock=clock, jev=client, fallback=fallback)
        policy.set_step(step, 0)
        state = SceneState()
        state.apply({"type": "snapshot", "scene_revision": 0, "payload": {
            "mode": "OBJECT", "active": None, "objects": [{"id": "mesh", "type": "MESH"}],
        }})
        result = evaluate("object_exists", state, step["check"]["params"])
        assert result.status == "unknown"
        await policy.process(state, result)
        clock.advance(20)
        decisions = bus.subscribe(Topic.DECISION)
        decision = await policy.process(state, result)
        metric = show("jev", metrics)
        assert client.attempts == 2
        assert all(status == 200 for status in client.statuses)
        if metric["status"] == "fallback":
            assert decision.kind == "help" and policy.degraded
            assert not decisions.empty()
        else:
            assert metric["status"] == "ok"
            assert decision is None or decision.kind == "help"
        assert metric["latency_ms"] < 1500


async def test_live_holo_localize():
    metrics = []
    fallback = Fallback(record=metrics.append)
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + key("HAI_API_KEY")},
                                 timeout=10) as http:
        client = HoloHttpClient(http)
        assert isinstance(client, HoloClient)
        point = await fallback.call("holo", lambda: client.localize(
            menu_png(), "the red menu row", timeout_s=5,
        ), 5, lambda: None)
        metric = show("holo", metrics)
        assert client.attempts == 1
        assert all(status == 200 or status == 429 or status >= 500 for status in client.statuses)
        assert isinstance(point, LocalizeResult), "Holo doit localiser sans fallback"
        assert 125 <= point.x < 875 and 500 <= point.y < 750, point
        assert abs(point.x - 500) <= 75 and abs(point.y - 625) <= 75, point
        assert metric["status"] == "ok"


async def test_live_gladia_upload_and_transcript():
    metrics = []
    fallback = Fallback(record=metrics.append)
    async with httpx.AsyncClient(headers={"x-gladia-key": key("GLADIA_API_KEY")},
                                 timeout=20) as http:
        client = GladiaHttpClient(http)
        assert isinstance(client, SttClient)
        audio = await asyncio.to_thread(spoken_wav)
        transcript = await fallback.call("gladia", lambda: client.transcribe(
            audio, encoding="wav", sample_rate=16000, language="fr",
        ), 90, lambda: None)
        metric = show("gladia", metrics)
        assert isinstance(transcript, Transcript)
        words = set(re.findall(r"\w+", transcript.text.casefold()))
        assert {"bonjour", "cube", "rouge", "menu"} <= words, transcript.text
        expected = "bonjour sélectionne le cube rouge ensuite ouvre le menu".split()
        recognized = re.findall(r"\w+", transcript.text.casefold())
        assert SequenceMatcher(None, expected, recognized).ratio() >= 0.8, transcript.text
        print("LIVE gladia transcript:", transcript.text)
        assert metric["status"] == "ok"
        assert client.attempts >= 3
        assert all(200 <= status < 300 for status in client.statuses)


async def test_live_linkup_search():
    metrics = []
    fallback = Fallback(record=metrics.append)
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + key("LINKUP_API_KEY")},
                                 timeout=20) as http:
        client = LinkupHttpClient(http)
        assert isinstance(client, SearchClient)
        hits = await fallback.call("linkup", lambda: client.search(
            "Blender manual add torus mesh primitive", depth="standard",
        ), 20, lambda: [])
        metric = show("linkup", metrics)
        assert hits and all(h.url.startswith("https://") and h.title for h in hits)
        assert metric["status"] == "ok"
