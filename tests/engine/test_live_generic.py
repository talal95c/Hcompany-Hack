# ruff: noqa: E402
"""E2E réel : LibreOffice Calc sous Xvfb + AT-SPI, services cloud réels (marqueur live)."""

import asyncio
import base64
import json
import os
import shutil
import signal
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("websockets", reason="Installez les dépendances : pip install -e '.[engine]'")
pytest.importorskip("openai", reason="Installez l'extra holo : pip install -e '.[holo]'")

from websockets.asyncio.client import connect

from engine.adapters import Rect, VisionAdapter, load_profile
from engine.adapters.vision import HoloAssertVerifier
from engine.bus import EventBus, Topic
from engine.bus.validation import validate
from engine.cache import TargetContext
from engine.checks import evaluate
from engine.config import EngineConfig
from engine.lesson import load_lesson
from engine.lesson.runtime import EngineRuntime
from engine.policy import HelpContext, HelpPolicy
from engine.services.adapters import build_clients

from .test_servers import send_ws

pytestmark = pytest.mark.live
HERE = Path(__file__).parent
DISPLAY = ":78"
APP = {"id": "libreoffice-calc", "name": "LibreOffice Calc", "version": "7.3.7",
       "sensor": "accessibility"}
LAUNCH = """
Xvfb {display} -screen 0 1600x1000x24 >/dev/null 2>&1 &
sleep 1
/usr/libexec/at-spi-bus-launcher --launch-immediately >/dev/null 2>&1 &
sleep 1
echo "$DBUS_SESSION_BUS_ADDRESS" > {env}
soffice -env:UserInstallation=file://{profile} --calc --norestore --nologo >/dev/null 2>&1 &
wait
"""


def require(*names):
    for name in names:
        if not os.getenv(name):
            pytest.skip(f"Variable {name} absente")
    for tool in ("Xvfb", "soffice", "import", "xdotool", "dbus-run-session"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} absent")


class Calc:
    """Calc réel : pont AT-SPI (python3 système), captures ImageMagick, saisie xdotool."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.env = {**os.environ, "DISPLAY": DISPLAY, "GTK_MODULES": "gail:atk-bridge",
                    "SAL_USE_VCLPLUGIN": "gtk3", "GNOME_ACCESSIBILITY": "1",
                    "NO_AT_BRIDGE": "0"}
        self.lock = asyncio.Lock()
        self.counter = 0
        self.timings: dict[str, list[float]] = {"atspi.find": [], "capture": []}

    async def start(self) -> None:
        env_file = self.tmp / "dbus.env"
        script = LAUNCH.format(display=DISPLAY, env=env_file, profile=self.tmp / "profile")
        self.session = subprocess.Popen(["dbus-run-session", "--", "bash", "-c", script],
                                        env=self.env, start_new_session=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        async with asyncio.timeout(20):
            while not env_file.exists() or not env_file.read_text().strip():
                await asyncio.sleep(0.2)
        self.env["DBUS_SESSION_BUS_ADDRESS"] = env_file.read_text().strip()
        self.bridge = await asyncio.create_subprocess_exec(
            "/usr/bin/python3", str(HERE / "calc_a11y_bridge.py"), env=self.env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        async with asyncio.timeout(60):
            while "error" in (frame := await self.call({"op": "frame"})):
                await asyncio.sleep(1)
        self.frame = frame
        await asyncio.sleep(2)

    async def call(self, request: dict) -> dict:
        async with self.lock:
            self.counter += 1
            line = json.dumps({"id": self.counter, "app": "soffice", **request}) + "\n"
            self.bridge.stdin.write(line.encode())
            await self.bridge.stdin.drain()
            reply = json.loads(await asyncio.wait_for(self.bridge.stdout.readline(), 15))
        result = reply["result"]
        if request["op"] == "find":
            self.timings["atspi.find"].append(result.pop("elapsed_ms"))
        return result

    async def capture(self) -> tuple[dict, bytes]:
        bounds = (await self.call({"op": "frame"}))["bounds"]
        start = time.perf_counter()
        geometry = f"{bounds['w']}x{bounds['h']}+{bounds['x']}+{bounds['y']}"
        process = await asyncio.create_subprocess_exec(
            "import", "-window", "root", "-crop", geometry, "+repage", "png:-",
            env=self.env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        image, _ = await process.communicate()
        self.timings["capture"].append((time.perf_counter() - start) * 1000)
        return bounds, image

    async def type_in(self, cell: tuple[float, float], text: str) -> None:
        for args in (["mousemove", str(round(cell[0])), str(round(cell[1])), "click", "1"],
                     ["type", "--delay", "40", text], ["key", "Return"]):
            process = await asyncio.create_subprocess_exec("xdotool", *args, env=self.env)
            await process.wait()

    async def cell(self, name: str) -> dict:
        result = await self.call({"op": "find", "query": {"role": "table cell", "name": name}})
        (node,) = result["nodes"]
        return node

    async def close(self) -> None:
        if getattr(self, "bridge", None):
            self.bridge.stdin.close()
            await self.bridge.wait()
        os.killpg(self.session.pid, signal.SIGTERM)
        await asyncio.to_thread(self.session.wait, 10)


class Shim:
    """Desktop minimal : relaie a11y.request vers AT-SPI et capture.request vers Xvfb."""

    def __init__(self, runtime: EngineRuntime, calc: Calc):
        self.runtime, self.calc = runtime, calc
        self.commands: list[tuple[dict, float]] = []
        self.condition = asyncio.Condition()

    async def start(self) -> None:
        self.ws = await connect(f"ws://127.0.0.1:{self.runtime.desktop.port}",
                                additional_headers={"Authorization": "Bearer live-token"})
        self.task = asyncio.create_task(self.collect())
        await send_ws(self.ws, "hello", {"app_version": "1", "platform": "linux",
                                        "capabilities": ["a11y"]})
        await send_ws(self.ws, "permissions", {"screen": True, "accessibility": True,
                                              "microphone": False})
        await send_ws(self.ws, "app.focus", {
            "app_id": "soffice", "name": self.calc.frame["name"],
            "version": self.calc.frame["version"],
            "window_title": self.calc.frame["title"], "window_bounds": self.calc.frame["bounds"],
            "scale": 1, "accessibility": "available"})

    async def collect(self) -> None:
        async for raw in self.ws:
            message = json.loads(raw)
            validate("desktop-ws", message)
            kind, payload = message["type"], message["payload"]
            if kind == "command":
                validate("commands", payload)
                async with self.condition:
                    self.commands.append((payload, time.perf_counter()))
                    self.condition.notify_all()
            elif kind == "a11y.request":
                asyncio.create_task(self.answer_a11y(payload))
            elif kind == "capture.request":
                asyncio.create_task(self.answer_capture(payload))

    async def answer_a11y(self, payload: dict) -> None:
        result = await self.calc.call({"op": payload["op"], "query": payload["query"]})
        await send_ws(self.ws, "a11y.result", {"request_id": payload["request_id"], **result})

    async def answer_capture(self, payload: dict) -> None:
        bounds, image = await self.calc.capture()
        await send_ws(self.ws, "capture.result", {
            "capture_id": str(uuid4()), "ui_revision": payload["ui_revision"],
            "crop": {"x": bounds["x"], "y": bounds["y"], "width": bounds["w"],
                     "height": bounds["h"]}, "scale": 1, "monitor_id": "xvfb",
            "request_id": payload["request_id"], "app": payload["app"],
            "image_ref": "data:image/png;base64," + base64.b64encode(image).decode()})

    async def wait_for(self, kind: str, after: int = 0, timeout: float = 30) -> tuple[dict, float]:
        async with asyncio.timeout(timeout), self.condition:
            await self.condition.wait_for(lambda: any(
                c["type"] == kind for c, _ in self.commands[after:]))
        return next((c, t) for c, t in self.commands[after:] if c["type"] == kind)

    async def close(self) -> None:
        await self.ws.close()
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


def stats(name: str, values: list[float]) -> None:
    values = sorted(values)
    p95 = values[min(len(values) - 1, round(0.95 * (len(values) - 1)))]
    print(f"LIVE {name} ms: p50={values[(len(values) - 1) // 2]:.1f} p95={p95:.1f} "
          f"max={values[-1]:.1f} n={len(values)}")


async def test_live_calc_end_to_end(tmp_path):
    require("HAI_API_KEY", "CODIV_API_KEY", "GLADIA_API_KEY", "LINKUP_API_KEY")
    calc = Calc(tmp_path)
    await calc.start()
    config = EngineConfig(session_id="s1", session_token="live-token",
                          learner_path=tmp_path / "learner.json", jev_timeout_s=8,
                          holo_timeout_s=20, a11y_timeout_s=5, a11y_poll_s=0.3,
                          no_progress_s=600, cooldown_s=0)
    clients = build_clients(config)
    assert set(clients) == {"holo", "jev", "stt", "search"}
    lesson = load_lesson(HERE / "fixtures/calc_lesson.json", allow_unproven=True)
    lesson["app"]["version"] = calc.frame["version"]
    runtime = EngineRuntime(config, lesson=lesson, **clients)
    latencies: list[dict] = []
    original = runtime.debug.record

    def record(event: dict) -> None:
        if event.get("kind") == "latency":
            latencies.append(event)
        original(event)

    runtime.debug.record = record
    await runtime.start()
    shim = Shim(runtime, calc)
    try:
        await shim.start()
        async with asyncio.timeout(15):
            while runtime.session.status != "OBSERVING":
                await asyncio.sleep(0.05)
        assert runtime.adapter is runtime.a11y

        # Échelle d'aide générique : texte, zone overlay a11y, pointeur au centre des bornes.
        await send_ws(shim.ws, "user.intent", {"text": "aide", "source": "clavier"})
        await shim.wait_for("say")
        count = len(shim.commands)
        await send_ws(shim.ws, "user.intent", {"text": "aide", "source": "clavier"})
        zone, _ = await shim.wait_for("highlight.rect", count)
        pointer, _ = await shim.wait_for("pointer", count)
        a1 = await calc.cell("A1")
        assert zone["payload"]["rect"] == a1["bounds"]
        window = Rect.from_dict(calc.frame["bounds"])
        x = window.x + pointer["payload"]["x"] * window.w / 1000
        y = window.y + pointer["payload"]["y"] * window.h / 1000
        assert Rect.from_dict(a1["bounds"]).contains(x, y), (x, y, a1["bounds"])
        print("LIVE pointer a11y:", pointer["payload"])

        # Étape 1 : vraie saisie, vrai arbre, vrai check element_value.
        count = len(shim.commands)
        await calc.type_in(Rect.from_dict(a1["bounds"]).center, "42")
        typed = time.perf_counter()
        _, received = await shim.wait_for("success", count)
        type_to_success = (received - typed) * 1000
        async with asyncio.timeout(5):
            while (runtime.session.step_id != "enter_formula"
                   or runtime.session.status != "OBSERVING"):
                await asyncio.sleep(0.05)

        # Étape 2 : formule réelle évaluée par Calc.
        count = len(shim.commands)
        a2 = await calc.cell("A2")
        await calc.type_in(Rect.from_dict(a2["bounds"]).center, "=A1*2")
        typed = time.perf_counter()
        _, received = await shim.wait_for("success", count)
        formula_to_success = (received - typed) * 1000
        async with asyncio.timeout(5):
            while runtime.session.status != "COMPLETE":
                await asyncio.sleep(0.05)
        print(f"LIVE saisie→✓ ms: étape1={type_to_success:.1f} étape2={formula_to_success:.1f}")

        # visual_assert : HoloVerifier réel sur une capture fraîche de la fenêtre.
        profile = load_profile(APP)
        verifier = HoloAssertVerifier(clients["holo"].client, app_context=profile.jev_context)
        vision = VisionAdapter(APP, profile, calc.capture, verifier, timeout_s=30)
        vision.permission = True
        vision.on_focus({"app_id": "soffice", "name": "LibreOffice Calc",
                         "window_title": calc.frame["title"],
                         "window_bounds": calc.frame["bounds"], "scale": 1})
        step = json.loads(json.dumps(runtime.session.lesson["steps"][0]))
        yes = {"assertion": "Dans la grille du tableur, la cellule A1 contient-elle le "
                            "nombre 42 ?", "min_confidence": 0.6}
        no = {"assertion": "Dans la grille du tableur, la cellule A1 est-elle vide ?",
              "min_confidence": 0.6}
        step["check"] = {"name": "visual_assert", "params": yes}
        step["known_errors"][0]["check"] = {"name": "visual_assert", "params": no}
        state = await vision.refresh(step)
        for _ in range(2):
            if all(v.answer is not None for v in state.verdicts.values()):
                break
            # Un délai cloud donne unknown (jamais pass) ; nouvelle capture fraîche.
            print("LIVE holo verify retry:", [v.detail for v in state.verdicts.values()])
            state = await vision.refresh(step)
        verdicts = {k: (v.answer, v.confidence, round(v.latency_ms)) for k, v in
                    state.verdicts.items()}
        print("LIVE holo verify:", verdicts)
        assert evaluate("visual_assert", state, yes).status == "pass"
        assert evaluate("visual_assert", state, no).status == "fail"

        # Pointage vision : Holo sur capture fenêtre, point validé dans le rect a11y attendu.
        bounds, image = await calc.capture()
        frame = Rect.from_dict(bounds)
        b1 = Rect.from_dict((await calc.cell("B1"))["bounds"])
        bus = EventBus()
        debug: list[dict] = []
        policy = HelpPolicy(replace(config, holo_timeout_s=20), bus, holo=clients["holo"],
                            debug=debug.append)
        commands = bus.subscribe(Topic.COMMAND)
        policy.set_step(runtime.session.lesson["steps"][0], 9)
        policy.level = 2
        target = TargetContext(APP["id"], APP["version"], (bounds["w"], bounds["h"]), 1,
                               "La cellule B1 de la feuille de calcul (colonne B, ligne 1)",
                               (bounds["x"], bounds["y"]), "xvfb", "fr", 0, True)
        milli = b1.milli(frame)
        margin = 4
        start = time.perf_counter()
        await policy.intent("aide", HelpContext(
            target=target, capture_id="live", image_png=image, require_visible=True,
            expected_rect=(milli.x - margin, milli.y - margin, milli.w + 2 * margin,
                           milli.h + 2 * margin)))
        holo_point_ms = (time.perf_counter() - start) * 1000
        emitted = []
        while not commands.empty():
            emitted.append(commands.get_nowait())
        print("LIVE holo pointer:", [(c["type"], c["payload"]) for c in emitted],
              [d for d in debug if d["kind"] == "point_rejected"])
        assert [c["type"] for c in emitted] in (["pointer"], ["say"])
        if emitted[0]["type"] == "say":
            assert any(d["kind"] == "point_rejected" or d["kind"] == "holo_unavailable"
                       for d in debug)

        # Jev réel avec le contexte du profil.
        start = time.perf_counter()
        decision = await clients["jev"].decide(
            {"check_status": "fail", "reason": "no_progress", "known_errors": [],
             "app": profile.service_context()}, timeout_s=15)
        jev_ms = (time.perf_counter() - start) * 1000
        assert decision.action in {"intervene", "wait"}

        # Linkup réel restreint aux domaines du profil ; Gladia réel avec le vocabulaire.
        start = time.perf_counter()
        hits = await runtime.docs_search("fonction SOMME LibreOffice Calc")
        linkup_ms = (time.perf_counter() - start) * 1000
        assert hits and all(h.url.startswith("https://") for h in hits)
        print("LIVE linkup domains:", sorted({h.url.split("/")[2] for h in hits})[:5])
        gladia_ms = None
        if shutil.which("espeak-ng") and shutil.which("ffmpeg"):
            sentence = "Bonjour. Sélectionne la cellule, puis ouvre la feuille de calcul."
            speech = subprocess.run(["espeak-ng", "-v", "fr-fr", "-s", "130", "--stdout",
                                     sentence],
                                    check=True, capture_output=True, timeout=10).stdout
            wav = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-ar", "16000",
                                  "-ac", "1", "-f", "wav", "pipe:1"], input=speech,
                                 check=True, capture_output=True, timeout=10).stdout
            start = time.perf_counter()
            transcript = await runtime.stt.transcribe(wav, encoding="wav", sample_rate=16000,
                                                      language="fr")
            gladia_ms = (time.perf_counter() - start) * 1000
            print("LIVE gladia:", transcript.text)
            heard = transcript.text.casefold()
            assert "cellul" in heard or "feuille" in heard, transcript.text

        by_stage: dict[str, list[float]] = {}
        for event in latencies:
            by_stage.setdefault(event["stage"], []).append(event["latency_ms"])
        for stage in ("a11y.find", "refresh", "event→check", "event→decision",
                      "decision→send", "capture.window"):
            if by_stage.get(stage):
                stats(stage, by_stage[stage])
        stats("atspi.find (pont)", calc.timings["atspi.find"])
        stats("capture fenêtre (import)", calc.timings["capture"])
        print(f"LIVE services ms: holo_pointer={holo_point_ms:.0f} jev={jev_ms:.0f} "
              f"linkup={linkup_ms:.0f} gladia={gladia_ms and round(gladia_ms)} "
              f"holo_verify={[v[2] for v in verdicts.values()]}")
    finally:
        await shim.close()
        await runtime.close()
        for client in clients.values():
            await client.aclose()
        await calc.close()
