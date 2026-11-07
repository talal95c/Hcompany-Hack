# ruff: noqa: E402
"""Rejeu d'un flux a11y façon Calc à travers le vrai WebSocket desktop."""

import asyncio
import base64
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("websockets", reason="Installez les dépendances : pip install -e '.[engine]'")

from websockets.asyncio.client import connect

from engine.bus import Topic
from engine.bus.validation import validate
from engine.config import EngineConfig
from engine.interfaces import FakeClock, VerifyResult
from engine.lesson import load_lesson
from engine.lesson.runtime import EngineRuntime

from .test_servers import png, send_ws

FIXTURES = Path(__file__).parent / "fixtures"
WINDOW = {"x": 57, "y": 50, "w": 1485, "h": 900}
CELLS = {"A1": (98, 185), "B1": (180, 185), "A2": (98, 202)}


class FakeCalc:
    """Desktop scripté : arbre AT-SPI minimal, captures fenêtre et journal des commandes."""

    def __init__(self, runtime: EngineRuntime):
        self.runtime = runtime
        self.values = dict.fromkeys(CELLS, "")
        self.error: str | None = None
        self.snapshot = 0
        self.messages: list[dict] = []
        self.commands: list[dict] = []
        self.requests: list[dict] = []
        self.condition = asyncio.Condition()
        self.action_started = asyncio.Event()
        self.action_release: asyncio.Event | None = None
        self.apply_actions = True

    def nodes(self, query: dict) -> list[dict]:
        found = []
        for name, (x, y) in CELLS.items():
            if query.get("role", "table cell") == "table cell" and query.get("name") == name:
                found.append({"ref": f"cell-{name}-{self.snapshot}", "role": "table cell",
                              "name": name, "value": self.values[name],
                              "states": ["enabled", "visible", "editable"],
                              "bounds": {"x": x, "y": y, "w": 82, "h": 17}})
        return found

    async def answer(self, message: dict) -> None:
        kind, payload = message["type"], message["payload"]
        if kind == "a11y.request":
            self.requests.append(payload)
            self.snapshot += 1
            if payload["op"] == "action":
                self.action_started.set()
                if self.action_release:
                    await self.action_release.wait()
                if self.apply_actions and payload["action"] == "set_value":
                    name = payload["ref"].split("-")[1]
                    self.values[name] = payload["value"]
                result = {"request_id": payload["request_id"], "snapshot_id": "action",
                          "complete": True, "nodes": []}
            elif self.error:
                result = {"request_id": payload["request_id"], "snapshot_id": None,
                          "complete": False, "nodes": [],
                          "error": {"code": self.error, "message": "Calc introuvable"}}
            else:
                result = {"request_id": payload["request_id"],
                          "snapshot_id": f"snap-{self.snapshot}", "complete": True,
                          "nodes": self.nodes(payload["query"])}
            await send_ws(self.ws, "a11y.result", result)
        elif kind == "capture.request":
            assert payload["scope"] == "window" and payload["crop"] is None
            await send_ws(self.ws, "capture.result", {
                "capture_id": str(uuid4()), "ui_revision": payload["ui_revision"],
                "crop": {"x": WINDOW["x"], "y": WINDOW["y"], "width": WINDOW["w"],
                         "height": WINDOW["h"]},
                "scale": 1, "monitor_id": "main", "request_id": payload["request_id"],
                "image_size": {"width": 1114, "height": 675},
                "app": payload["app"], "image_ref": "data:image/png;base64,"
                + base64.b64encode(png(1114, 675)).decode()})

    async def collect(self) -> None:
        async for raw in self.ws:
            message = json.loads(raw)
            validate("desktop-ws", message)
            async with self.condition:
                self.messages.append(message)
                if message["type"] == "command":
                    validate("commands", message["payload"])
                    self.commands.append(message["payload"])
                self.condition.notify_all()
            if message["type"] == "a11y.request" and message["payload"]["op"] == "action":
                self.runtime.spawn(self.answer(message))
            else:
                await self.answer(message)

    async def start(self) -> None:
        self.ws = await connect(f"ws://127.0.0.1:{self.runtime.desktop.port}",
                                additional_headers={"Authorization": "Bearer calc-token"})
        self.task = asyncio.create_task(self.collect())
        await send_ws(self.ws, "hello", {"app_version": "1", "platform": "linux",
                                        "capabilities": ["a11y"]})
        await send_ws(self.ws, "permissions", {"screen": True, "accessibility": True,
                                              "microphone": False})
        await self.focus("soffice")

    async def focus(self, app_id: str, name: str = "LibreOffice Calc") -> None:
        await send_ws(self.ws, "app.focus", {
            "app_id": app_id, "name": name,
            "version": self.runtime.app["version"],
            "window_title": "Sans nom 1 - LibreOffice Calc", "window_bounds": WINDOW,
            "scale": 1, "accessibility": "available"})
        await self.barrier()

    async def barrier(self) -> None:
        nonce = str(uuid4())
        await send_ws(self.ws, "ping", {"nonce": nonce})
        async with asyncio.timeout(3), self.condition:
            await self.condition.wait_for(lambda: any(
                m["type"] == "pong" and m["payload"]["nonce"] == nonce for m in self.messages))

    async def wait_commands(self, count: int) -> None:
        async with asyncio.timeout(3), self.condition:
            await self.condition.wait_for(lambda: len(self.commands) >= count)

    async def close(self) -> None:
        await self.ws.close()
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


async def start_runtime(tmp_path, **clients) -> tuple[EngineRuntime, FakeCalc]:
    runtime = EngineRuntime(
        EngineConfig(session_id="s1", session_token="calc-token",
                     learner_path=tmp_path / "learner.json"),
        lesson=load_lesson(FIXTURES / "calc_lesson.json", allow_unproven=True),
        clock=FakeClock(), **clients)
    await runtime.start()
    loops = [t for t in runtime.tasks if t.get_coro().__name__ in {"timer", "observe_app"}]
    for task in loops:
        task.cancel()
    await asyncio.gather(*loops, return_exceptions=True)
    desktop = FakeCalc(runtime)
    await desktop.start()
    return runtime, desktop


async def observe(runtime, desktop, expected: list[str], latencies: list[float]) -> list[dict]:
    before = len(desktop.commands)
    start = time.perf_counter()
    await runtime.observe_once()
    await runtime.commands.join()
    await desktop.wait_commands(before + len(expected))
    await desktop.barrier()
    fresh = desktop.commands[before:]
    assert [c["type"] for c in fresh] == expected
    if fresh:
        latencies.append((time.perf_counter() - start) * 1000)
    return fresh


def summary(name, values):
    values = sorted(values)
    print(f"CALC {name} ms: p50={values[(len(values) - 1) // 2]:.3f} "
          f"max={values[-1]:.3f} n={len(values)}")


async def test_calc_a11y_replay_help_ladder_and_success(tmp_path):
    class NoHolo:
        async def localize(self, *args, **kwargs):
            pytest.fail("Le centre des bornes a11y suffit au pointage")

    runtime, desktop = await start_runtime(tmp_path, holo=NoHolo())
    decisions = runtime.bus.subscribe(Topic.DECISION)
    latencies: list[float] = []
    try:
        assert runtime.adapter is runtime.a11y
        await observe(runtime, desktop, [], latencies)
        assert runtime.session.status == "OBSERVING"
        assert {r["op"] for r in desktop.requests} == {"find"}
        assert all(r["app"] == "libreoffice-calc" for r in desktop.requests)

        runtime.clock.advance(20)
        (say,) = await observe(runtime, desktop, ["say"], latencies)
        assert say["payload"]["text"] == runtime.session.step["why"]

        desktop.values["B1"] = "42"
        runtime.clock.advance(31)
        (zone,) = await observe(runtime, desktop, ["highlight.rect"], latencies)
        async with asyncio.timeout(1):
            while (not runtime.help_context.target
                   or not runtime.targets.get_target(runtime.help_context.target)):
                await asyncio.sleep(0)
        before = len(desktop.commands)
        await send_ws(desktop.ws, "user.intent", {"text": "aide", "source": "clavier"})
        await desktop.wait_commands(before + 1)
        pointer = desktop.commands[before]
        assert zone["payload"]["rect"] == {"x": 98, "y": 185, "w": 82, "h": 17}
        assert zone["payload"]["app"] == "libreoffice-calc"
        assert (pointer["payload"]["x"], pointer["payload"]["y"]) == (55, 159)
        assert pointer["payload"]["ref"].startswith("cell-A1-")
        assert pointer["payload"]["snapshot_id"].startswith("snap-")

        desktop.values.update(A1="42", B1="")
        await observe(runtime, desktop, ["success"], latencies)
        assert runtime.session.step_id == "enter_formula"
        assert runtime.session.status == "OBSERVING"

        desktop.values["A2"] = "84"
        await observe(runtime, desktop, ["success"], latencies)
        assert runtime.session.status == "COMPLETE"
        seen = []
        while not decisions.empty():
            d = decisions.get_nowait()
            seen.append((d.step_id, d.kind, d.reason, d.level))
        assert seen == [
            ("enter_value", "help", "no_progress", 1),
            ("enter_value", "help", "known_error:wrong_cell", 2),
            ("enter_value", "help", "explicit", 3),
            ("enter_value", "success", "check_pass", 3),
            ("enter_formula", "success", "check_pass", 0),
        ]
        summary("observe→command", latencies)
    finally:
        await desktop.close()
        await runtime.close()


async def test_calc_a11y_failure_falls_back_to_vision_without_false_pass(tmp_path):
    class Verifier:
        def __init__(self):
            self.calls = 0

        async def verify(self, image_png, assertion, *, timeout_s):
            self.calls += 1
            return VerifyResult(True, 0.99, 1)

    verifier = Verifier()
    runtime, desktop = await start_runtime(tmp_path, verifier=verifier)
    try:
        desktop.error = "APP_NOT_FOUND"
        desktop.values["A1"] = "42"
        await runtime.observe_once()
        assert runtime.adapter is runtime.vision and "accessibility" in runtime.router.degraded
        await runtime.observe_once()
        # Un check exact reste unknown en vision : pas de ✓ inventé.
        assert runtime.session.status in {"PAUSED", "READY"}
        assert not any(c["type"] == "success" for c in desktop.commands)
        assert verifier.calls == 0
        desktop.error = None
        await desktop.focus("libreoffice-calc")
        assert runtime.adapter is runtime.a11y
        await runtime.observe_once()
        await runtime.observe_once()
        await runtime.commands.join()
        await desktop.wait_commands(1)
        assert [c["type"] for c in desktop.commands] == ["success"]
    finally:
        await desktop.close()
        await runtime.close()


async def test_calc_wrong_window_or_disconnect_pauses(tmp_path):
    runtime, desktop = await start_runtime(tmp_path)
    try:
        await runtime.observe_once()
        assert runtime.session.status == "OBSERVING"
        await desktop.focus("gedit", "Éditeur de texte")
        assert runtime.adapter is None and not runtime.app_ready()
        desktop.values["A1"] = "42"
        await runtime.observe_once()
        await runtime.tick()
        assert runtime.session.status == "PAUSED"
        await desktop.close()
        async with asyncio.timeout(2):
            while runtime.a11y.focus is not None or runtime.desktop.clients:
                await asyncio.sleep(0.01)
        await runtime.observe_once()
        assert runtime.session.status == "PAUSED"
    finally:
        await runtime.close()
