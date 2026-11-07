# ruff: noqa: E402

import asyncio
import json
import math
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("httpx", reason="Installez les dépendances : pip install -e '.[engine]'")
pytest.importorskip("websockets", reason="Installez les dépendances : pip install -e '.[engine]'")

from websockets.asyncio.client import connect

from engine.bus import Topic
from engine.bus.validation import validate
from engine.config import EngineConfig
from engine.interfaces import FakeClock, HoloClient, JevClient, JevDecision, LocalizeResult
from engine.learner import LearnerMemory
from engine.lesson import load_lesson
from engine.lesson.runtime import EngineRuntime

from .test_servers import capture, event, send_event, send_ws

FIXTURES = Path(__file__).parent / "fixtures"


class FastHolo:
    def __init__(self):
        self.calls = 0

    async def localize(
        self, image_png: bytes, description: str, *, timeout_s: float,
    ) -> LocalizeResult:
        self.calls += 1
        assert image_png.startswith(b"\x89PNG")
        assert "Sphère" in description
        return LocalizeResult(500, 625, 0.99, 0, True)

    async def verify_point(self, *args, **kwargs):
        return True


class StubJev:
    def __init__(self, delay: float = 0):
        self.delay = delay
        self.calls = 0
        self.cancelled = False

    async def decide(self, context: dict, *, timeout_s: float) -> JevDecision:
        self.calls += 1
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return JevDecision("intervene", "Blocage", 0)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class Replay:
    def __init__(self, runtime: EngineRuntime):
        self.runtime = runtime
        self.clock = runtime.clock
        self.events = runtime.bus.subscribe(Topic.EVENT)
        self.decisions = runtime.bus.subscribe(Topic.DECISION)
        self.seen_decisions = []
        self.commands: list[tuple[dict, float]] = []
        self.messages: list[tuple[dict, float]] = []
        self.latencies = []
        self.condition = asyncio.Condition()
        self.collectors = []

    async def wait_for(self, predicate):
        async with asyncio.timeout(3):
            async with self.condition:
                await self.condition.wait_for(predicate)

    async def collect_ws(self):
        async for raw in self.ws:
            message = json.loads(raw)
            validate("desktop-ws", message)
            async with self.condition:
                self.messages.append((message, time.perf_counter()))
                if message["type"] == "command":
                    command = message["payload"]
                    validate("commands", command)
                    self.commands.append((command, time.perf_counter()))
                    if command["type"] == "input.action":
                        await send_ws(self.ws, "input.result", {
                            "command_id": command["command_id"], "status": "ok", "detail": "Clic",
                        })
                self.condition.notify_all()

    async def collect_addon(self):
        while line := await self.reader.readline():
            command = json.loads(line)
            validate("commands", command)
            async with self.condition:
                self.commands.append((command, time.perf_counter()))
                self.condition.notify_all()

    async def start(self):
        await self.runtime.start()
        # Les ticks de cette recette suivent les offsets enregistrés, pas le temps mural.
        timers = [t for t in self.runtime.tasks if t.get_coro().__name__ == "timer"]
        for task in timers:
            task.cancel()
        await asyncio.gather(*timers, return_exceptions=True)
        self.ws = await connect(f"ws://127.0.0.1:{self.runtime.desktop.port}",
                                additional_headers={"Authorization": "Bearer replay-token"})
        self.collectors.append(asyncio.create_task(self.collect_ws()))
        await send_ws(self.ws, "hello", {"app_version": "1", "platform": "linux",
                                        "capabilities": []})
        await self.wait_for(lambda: bool(self.messages))
        await send_ws(self.ws, "permissions", {"screen": True, "accessibility": True,
                                              "microphone": True})
        await self.barrier()
        self.reader, self.writer = await asyncio.open_connection(
            "127.0.0.1", self.runtime.addon.port,
        )
        self.collectors.append(asyncio.create_task(self.collect_addon()))

    async def barrier(self):
        nonce = str(uuid4())
        await send_ws(self.ws, "ping", {"nonce": nonce})
        await self.wait_for(lambda: any(m["type"] == "pong" and m["payload"]["nonce"] == nonce
                                        for m, _ in self.messages))

    def collect_decisions(self):
        fresh = []
        while not self.decisions.empty():
            decision = self.decisions.get_nowait()
            fresh.append(decision)
            self.seen_decisions.append(decision)
        return fresh

    async def row(self, message: dict, expected_commands: tuple[str, ...] = ()):
        validate("addon-events", message)
        self.clock.advance(message["ts_monotonic_ms"] / 1000 - self.clock.monotonic())
        command_count, message_count = len(self.commands), len(self.messages)
        start = time.perf_counter()
        await send_event(self.writer, message)
        async with asyncio.timeout(3):
            while (await self.events.get())["event_id"] != message["event_id"]:
                pass
            async with self.runtime.lock:
                pass
        await self.runtime.commands.join()
        if expected_commands:
            await self.wait_for(
                lambda: len(self.commands) >= command_count + len(expected_commands),
            )
        await self.barrier()
        fresh = self.collect_decisions()
        actual = [c["type"] for c, _ in self.commands[command_count:]]
        assert actual == list(expected_commands), (message["seq"], actual)
        if fresh:
            sent = [t for _, t in self.commands[command_count:]]
            if not sent:
                sent = [t for m, t in self.messages[message_count:] if m["type"] != "pong"]
            assert sent
            self.latencies.append((max(sent) - start) * 1000)
        return fresh

    async def intent(self, text: str):
        await send_ws(self.ws, "user.intent", {"text": text, "source": "bouton"})
        await self.barrier()
        self.collect_decisions()

    async def close(self):
        await self.ws.close()
        self.writer.close()
        await self.writer.wait_closed()
        for task in self.collectors:
            task.cancel()
        await asyncio.gather(*self.collectors, return_exceptions=True)
        await self.runtime.close()


@asynccontextmanager
async def replay(tmp_path, *, lesson=None, jev=None, holo=None):
    runtime = EngineRuntime(
        EngineConfig(session_id="s1", session_token="replay-token",
                     learner_path=tmp_path / "learner.json"),
        lesson=lesson or load_lesson(FIXTURES / "donut_lesson.json"),
        clock=FakeClock(), holo=holo, jev=jev,
    )
    harness = Replay(runtime)
    await harness.start()
    try:
        yield harness
    finally:
        await harness.close()


def summary(name, values):
    assert values
    values = sorted(values)
    print(f"E2E {name} ms: p50={values[(len(values) - 1) // 2]:.3f} "
          f"p95={values[math.ceil(len(values) * .95) - 1]:.3f} max={values[-1]:.3f}")


async def test_donut_replay_exact_decisions_and_latency(tmp_path):
    holo, jev = FastHolo(), StubJev()
    assert isinstance(holo, HoloClient) and isinstance(jev, JevClient)
    rows = [json.loads(line) for line in
            (FIXTURES / "donut_session.jsonl").read_text().splitlines()]
    validate("lesson", load_lesson(FIXTURES / "donut_lesson.json"))
    expected = {1: ("request_snapshot",), 4: ("say",), 9: ("success",), 12: ("say",),
                13: ("highlight", "open_menu"), 21: ("success",)}
    async with replay(tmp_path, holo=holo, jev=jev) as h:
        for row in rows:
            seq = row["seq"]
            if seq == 11:
                # Délégation confirmée ; un clic consomme sa capture avant la suite pédagogique.
                token = str(uuid4())
                await h.intent(json.dumps({"intent": "fais-le", "consent_token": token,
                                           "delegation_confirmed": True, "wants_to_learn": False}))
                assert h.runtime.session.status == "ACTING"
                await send_ws(h.ws, "capture.result", capture(h.runtime, "action-frame"))
                await h.barrier()
                count = len(h.commands)
                result = await h.runtime.input_action({"type": "click", "x": 500, "y": 500})
                assert result["status"] == "ok"
                await h.wait_for(lambda: len(h.commands) == count + 2)
                action = h.commands[count][0]
                assert action["type"] == "input.action"
                assert action["payload"]["consent_token"] == token
                assert action["payload"]["capture_id"] == "action-frame"
                assert h.commands[count + 1][0]["type"] == "request_snapshot"
                assert h.runtime.help_context.image_png is None
            if seq == 19:
                await h.intent("chut")
                before = len(h.commands)
            if seq == 20:
                assert h.runtime.policy.muted
                assert len(h.commands) == before
                await h.intent("reprends")
            fresh = await h.row(row, expected.get(seq, ()))
            if seq == 5:
                assert not fresh  # L'erreur persistante ne répète pas l'indice.
            if seq == 7:
                assert h.runtime.policy.deferred == "known_error:wrong_cube"
            if seq == 14:
                assert fresh[0].level == 2 and holo.calls == 0
                assert not any(c["type"] == "pointer" for c, _ in h.commands)
                await send_ws(h.ws, "capture.result", capture(h.runtime, "pointer-frame"))
                await h.barrier()
                if h.runtime.preloader.task:
                    await h.runtime.preloader.task
                if h.runtime.policy.level < 3:
                    await h.intent("aide")
                h.collect_decisions()
                assert h.commands[-1][0]["type"] == "pointer"
                assert holo.calls == 1
                assert h.commands[-1][0]["payload"]["capture_id"] == "pointer-frame"
            if seq == 17:
                assert not fresh and h.runtime.policy.deferred == "undos"
            if seq == 19:
                assert not fresh
        assert [(d.kind, d.reason, d.level, d.step_id) for d in h.seen_decisions] == [
            ("help", "known_error:wrong_cube", 1, "add_torus"),
            ("success", "check_pass", 1, "add_torus"),
            ("help", "no_progress", 1, "add_sphere"),
            ("help", "no_progress", 2, "add_sphere"),
            ("help", "no_progress", 2, "add_sphere"),
            ("help", "explicit", 3, "add_sphere"),
            ("help", "undos", 3, "add_sphere"),
            ("help", "no_progress", 3, "add_sphere"),
            ("success", "check_pass", 3, "add_sphere"),
        ]
        assert h.runtime.session.status == "COMPLETE"
        assert jev.calls == 4 and holo.calls == 1
        assert [c["type"] for c, _ in h.commands].count("say") == 2
        skills = LearnerMemory(h.runtime.config.learner_path).skills
        assert skills["add_torus"].max_help_level_used == 1
        assert skills["add_sphere"].max_help_level_used == 3
        assert all(s.last_review is not None for s in skills.values())
        checks = list(h.runtime.debug.samples["check"])
        summary("donut event→decision", h.latencies)
        summary("donut check", checks)
        assert max(checks) < 10
        assert max(h.latencies) < 50
        assert not any(e.get("kind") == "task_error" for e in h.runtime.debug.events)


async def test_slow_jev_real_socket_timeout_and_no_late_decision(tmp_path):
    jev = StubJev(delay=1)
    async with replay(tmp_path, jev=jev) as h:
        await h.row(event(), ("request_snapshot",))
        await h.row(event("snapshot", 2, 0, mode="OBJECT", active=None,
                          objects=[{"id": "mesh", "type": "MESH"}]))
        message = event("heartbeat", 3, 0, uptime_ms=20000)
        message["ts_monotonic_ms"] = 20000
        fresh = await h.row(message, ("say",))
        assert [(d.kind, d.level) for d in fresh] == [("help", 1)]
        assert jev.calls == 1 and jev.cancelled
        assert h.runtime.policy.degraded
        assert h.runtime.fallback.health["jev"].consecutive_failures == 1
        message = event("heartbeat", 4, 0, uptime_ms=21000)
        message["ts_monotonic_ms"] = 21000
        assert not await h.row(message)
        assert jev.calls == 1 and len(h.seen_decisions) == 1
        errors = [m for m, _ in h.messages if m["type"] == "error"]
        assert [m["payload"]["code"] for m in errors] == ["degraded"]
        latency = h.runtime.debug.metrics()["jev"]["max"]
        print(f"E2E slow Jev fallback ms: {latency:.3f}")
        # Le budget local exclut cet appel volontairement plus lent que le délai Jev.
        assert 790 <= latency < 1500
        assert max(h.runtime.debug.samples["check"]) < 10


async def test_loaded_modifier_material_shading_runtime(tmp_path):
    base = {"id": "torus", "type": "MESH", "primitive_provenance": "torus",
                       "mesh": {"verts": 576, "edges": 1152, "polys": 576}}
    path = FIXTURES / "extended_lesson.json"
    lesson = load_lesson(path)
    modified = {**base, "modifiers": [{"type": "SUBSURF", "levels": 2}]}
    colored = {**modified, "materials": [{"base_color": [1, 0.2, 0.1, 1]}]}
    async with replay(tmp_path, lesson=lesson) as h:
        await h.row(event(), ("request_snapshot",))
        await h.row(event("snapshot", 2, 0, mode="OBJECT", active=None, objects=[]))
        for seq, revision, obj, passes in [
            (3, 1, base, False), (4, 2, modified, True), (5, 2, modified, False),
            (6, 3, {**modified, "materials": [{"base_color": [0, 0, 0, 1]}]}, False),
            (7, 4, colored, True), (8, 4, colored, False),
            (9, 5, {**colored, "mesh": {**base["mesh"], "shading_smooth": False}}, False),
            (10, 6, {**colored, "mesh": {**base["mesh"], "shading_smooth": True}}, True),
        ]:
            message = event("snapshot", seq, revision, mode="OBJECT", active="torus", objects=[obj])
            await h.row(message, ("success",) if passes else ())
        assert h.runtime.session.status == "COMPLETE"
        assert [d.kind for d in h.seen_decisions] == ["success"] * 3
        assert [c["type"] for c, _ in h.commands] == ["request_snapshot"] + ["success"] * 3
        assert all(s.successes_without_help == 1 for s in h.runtime.learner.skills.values())
        summary("extended checks event→decision", h.latencies)
        summary("extended check", list(h.runtime.debug.samples["check"]))
        assert max(h.latencies) < 50
        assert max(h.runtime.debug.samples["check"]) < 10
