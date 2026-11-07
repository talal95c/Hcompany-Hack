# ruff: noqa: E402

import asyncio
import base64
import binascii
import json
import os
import signal
import struct
import sys
import time
import zlib
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

httpx = pytest.importorskip(
    "httpx", reason="Installez les dépendances : pip install -e '.[engine]'",
)
pytest.importorskip("websockets", reason="Installez les dépendances : pip install -e '.[engine]'")

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from engine.bus import Topic
from engine.bus.servers import Correlator, EventBuffer
from engine.bus.validation import validate
from engine.config import EngineConfig
from engine.interfaces import FakeClock, LocalizeResult, Transcript
from engine.lesson import load_lesson
from engine.lesson.runtime import EngineRuntime, decode_capture

ROOT = Path(__file__).resolve().parents[2]


def lesson():
    return load_lesson(ROOT / "tests/engine/fixtures/single_lesson.json")


@pytest.fixture
async def runtime(tmp_path):
    config = EngineConfig(session_id="s1", session_token="private-test-token",
                          learner_path=tmp_path / "learner.json")
    engine = EngineRuntime(config, clock=FakeClock(), lesson=lesson())
    await engine.start()
    try:
        yield engine
    finally:
        await asyncio.wait_for(engine.close(), 2)


def event(kind="hello", seq=1, revision=0, **payload):
    if kind == "hello":
        payload = {"blender_version": "4.5.9", "capabilities": []}
    message = {"schema_version": "1.0", "session_id": "s1", "event_id": str(uuid4()),
               "seq": seq, "type": kind, "ts_monotonic_ms": 0,
               "scene_revision": revision, "payload": payload}
    validate("addon-events", message)
    return message


async def send_event(writer, message):
    writer.write((json.dumps(message) + "\n").encode())
    await writer.drain()


async def read_command(reader):
    command = json.loads(await asyncio.wait_for(reader.readline(), 1))
    validate("commands", command)
    return command


async def send_ws(ws, kind, payload):
    message = {"schema_version": "1.0", "session_id": "s1", "message_id": str(uuid4()),
               "reply_to": None, "type": kind, "payload": payload}
    validate("desktop-ws", message)
    await ws.send(json.dumps(message))


async def read_ws(ws, kind=None):
    async with asyncio.timeout(2):
        while True:
            message = json.loads(await ws.recv())
            validate("desktop-ws", message)
            if kind is None or message["type"] == kind:
                return message


async def desktop(runtime):
    ws = await connect(f"ws://127.0.0.1:{runtime.desktop.port}",
                       additional_headers={"Authorization": "Bearer private-test-token"})
    await send_ws(ws, "hello", {"app_version": "1", "platform": "linux", "capabilities": []})
    assert (await read_ws(ws, "lesson.state"))["payload"]["step_id"]
    return ws


async def addon(runtime):
    reader, writer = await asyncio.open_connection("127.0.0.1", runtime.addon.port)
    await send_event(writer, event())
    assert (await read_command(reader))["type"] == "request_snapshot"
    return reader, writer


async def synchronized(runtime, writer, ws, seq=2):
    await send_event(writer, event("snapshot", seq, 0, mode="OBJECT", active=None, objects=[]))
    async with asyncio.timeout(1):
        while runtime.session.status != "OBSERVING":
            await asyncio.sleep(0)
    await send_ws(ws, "ping", {"nonce": "barrier"})
    await read_ws(ws, "pong")


async def test_handshake_auth_origins_and_hello(runtime):
    url = f"ws://127.0.0.1:{runtime.desktop.port}"
    for token, origin, expected in [("bad", None, 401), ("private-test-token", "https://bad", 403)]:
        with pytest.raises(InvalidStatus) as caught:
            await connect(url + "?token=" + token, origin=origin)
        assert caught.value.response.status_code == expected
    for origin in (None, "tauri://localhost", "http://tauri.localhost"):
        async with connect(url + "?token=private-test-token", origin=origin) as ws:
            await send_ws(ws, "hello", {"app_version": "1", "platform": "linux",
                                       "capabilities": []})
            state = await read_ws(ws)
            assert state["type"] == "lesson.state"
            await send_ws(ws, "ping", {"nonce": "n"})
            assert (await read_ws(ws))["payload"]["nonce"] == "n"
            await ws.send('{"secret":"must-not-appear"}')
            assert (await read_ws(ws))["type"] == "error"
    assert "must-not-appear" not in json.dumps(list(runtime.debug.events))


async def test_addon_invalid_auth_envelope_and_line_limit(runtime):
    for data in [b'{}\n', b'x' * (1024 * 1024 + 1) + b'\n']:
        reader, writer = await asyncio.open_connection("127.0.0.1", runtime.addon.port)
        writer.write(data)
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b""
        writer.close()
        await writer.wait_closed()
    for message in [event("heartbeat", uptime_ms=1), {**event(), "session_id": "wrong"}]:
        reader, writer = await asyncio.open_connection("127.0.0.1", runtime.addon.port)
        await send_event(writer, message)
        assert await asyncio.wait_for(reader.read(), 1) == b""
        writer.close()


async def test_seq_gap_dedupe_reconnect(runtime):
    queue = runtime.bus.subscribe(Topic.EVENT)
    reader, writer = await addon(runtime)
    first_generation = runtime.session.generation
    heartbeat = event("heartbeat", 2, uptime_ms=1)
    await send_event(writer, heartbeat)
    received = [await asyncio.wait_for(queue.get(), 1), await asyncio.wait_for(queue.get(), 1)]
    await send_event(writer, heartbeat)
    await send_event(writer, event("heartbeat", 4, uptime_ms=2))
    assert (await read_command(reader))["type"] == "request_snapshot"
    async with asyncio.timeout(1):
        while len(received) < 3:
            received.append(await queue.get())
    assert [e["seq"] for e in received] == [1, 2, 4]
    assert runtime.session.generation > first_generation
    writer.close()
    await writer.wait_closed()
    async with asyncio.timeout(1):
        while runtime.addon.writer:
            await asyncio.sleep(0)
    reader, writer = await addon(runtime)
    assert runtime.capture is None and not runtime.state.recent
    writer.close()


async def test_correlated_addon_result_cached_and_timeout(runtime):
    reader, writer = await addon(runtime)
    command = runtime.make_command("open_menu", {"menu_id": "VIEW3D_MT_mesh_add",
                                                "area_id": "a", "region_id": "r"})
    task = asyncio.create_task(runtime.addon.correlation.request(command, runtime.addon.send))
    assert await read_command(reader) == command
    await send_event(writer, event("command.result", 2, command_id=command["command_id"],
                                   status="ok", detail="Menu ouvert", scene_revision=0))
    result = await task
    assert result["status"] == "ok"
    assert await runtime.addon.correlation.request(command, runtime.addon.send) == result
    command = {**runtime.make_command("request_snapshot", {}), "deadline_ms": 1}
    with pytest.raises(TimeoutError):
        await runtime.addon.correlation.request(command, runtime.addon.send)
    cached = await runtime.addon.correlation.request(command, runtime.addon.send)
    assert cached["status"] == "expired"
    writer.close()


async def test_scene_aggregation_preserves_command_order():
    buffer = EventBuffer()
    await buffer.put(event("scene.changed", 1, 1, changed_ids=["a"],
                           objects=[{"id": "a", "type": "MESH"}]))
    await buffer.put(event("scene.changed", 2, 2, changed_ids=["b"], objects=[{"id": "b"}]))
    await buffer.put(event("command.result", 3, 2, command_id="c", status="ok",
                           detail="ok", scene_revision=2))
    await buffer.put(event("scene.changed", 4, 3, changed_ids=["a"], objects=[]))
    merged = await buffer.get()
    assert merged["payload"]["changed_ids"] == ["a", "b"]
    assert (await buffer.get())["type"] == "command.result"
    assert (await buffer.get())["payload"]["objects"] == []


def png(width=1, height=1):
    def chunk(name, body):
        return struct.pack("!I", len(body)) + name + body + struct.pack(
            "!I", binascii.crc32(name + body) & 0xffffffff,
        )
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height,
        8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00" * height)) + chunk(
            b"IEND", b"",
        )


def capture(runtime, capture_id="cap"):
    payload = {"capture_id": capture_id, "ui_revision": runtime.ui_revision,
            "crop": {"x": 0, "y": 0, "width": 1, "height": 1}, "scale": 2,
            "monitor_id": "main", "image_ref": "data:image/png;base64,"
            + base64.b64encode(png()).decode()}
    payload["request_id"] = str(uuid4())
    runtime.pointer_request = {"request_id": payload["request_id"], "crop": payload["crop"],
                               "generation": runtime.session.generation,
                               "epoch": runtime.policy.capture_epoch, "at": time.monotonic()}
    return payload


async def permissions(ws):
    await send_ws(ws, "permissions", {"screen": True, "accessibility": True, "microphone": True})
    await send_ws(ws, "ping", {"nonce": "permissions"})
    await read_ws(ws, "pong")


async def consent(ws, *, delegation=False):
    intent = {"intent": "fais-le", "consent_token": str(uuid4())}
    if delegation:
        intent.update(delegation_confirmed=True, wants_to_learn=False)
    await send_ws(ws, "user.intent", {"source": "bouton", "text": json.dumps(intent)})
    return intent["consent_token"]


async def test_consent_capture_consumption_and_expiry(runtime):
    reader, writer = await addon(runtime)
    ws = await desktop(runtime)
    try:
        await synchronized(runtime, writer, ws)
        await permissions(ws)
        await consent(ws)
        assert (await read_ws(ws, "error"))["payload"]["code"] == "consent_required"
        assert await runtime.input_action({"type": "click", "x": 1, "y": 2}) is None
        assert (await read_ws(ws, "error"))["payload"]["code"] == "consent_required"
        token = await consent(ws, delegation=True)
        assert (await read_ws(ws, "lesson.state"))["payload"]["status"] == "ACTING"
        assert await runtime.input_action({"type": "click"}) is None
        assert (await read_ws(ws, "error"))["payload"]["code"] == "capture_required"
        await send_ws(ws, "capture.result", capture(runtime))
        await send_ws(ws, "ping", {"nonce": "capture"})
        await read_ws(ws, "pong")
        task = asyncio.create_task(runtime.input_action({"type": "click", "x": 100, "y": 200}))
        command = (await read_ws(ws, "command"))["payload"]
        assert command["payload"]["consent_token"] == token
        assert command["payload"]["capture_id"] == "cap"
        await send_ws(ws, "input.result", {"command_id": command["command_id"],
                                          "status": "ok", "detail": "clic"})
        assert (await task)["status"] == "ok"
        assert (await read_command(reader))["type"] == "request_snapshot"
        await synchronized(runtime, writer, ws, seq=3)
        assert await runtime.input_action({"type": "click"}) is None
        assert (await read_ws(ws, "error"))["payload"]["code"] == "capture_required"
        await send_ws(ws, "capture.result", capture(runtime))
        assert (await read_ws(ws, "error"))["payload"]["code"] == "invalid_message"
        await send_ws(ws, "capture.result", capture(runtime, "cap2"))
        await send_ws(ws, "ping", {"nonce": "new"})
        await read_ws(ws, "pong")
        runtime.clock.advance(60)
        assert await runtime.input_action({"type": "click"}) is None
        assert (await read_ws(ws, "error"))["payload"]["code"] == "consent_required"
    finally:
        await ws.close()
        writer.close()


@pytest.mark.parametrize("reference", [
    "buffer:cap", "file:///secret", "data:image/jpeg;base64,AA==",
    "data:image/png;base64,not-base64",
])
async def test_capture_errors(runtime, reference):
    ws = await desktop(runtime)
    try:
        await permissions(ws)
        await send_ws(ws, "capture.result", {**capture(runtime), "image_ref": reference})
        assert (await read_ws(ws, "error"))["payload"]["code"] == "invalid_message"
    finally:
        await ws.close()


async def test_capture_localization_and_audio(runtime):
    class Holo:
        async def localize(self, image_png, description, *, timeout_s):
            assert image_png == png()
            return LocalizeResult(500, 500, None, 0, True)

        async def verify_point(self, *args, **kwargs):
            return True

    class Stt:
        async def transcribe(self, audio, **kwargs):
            assert audio == b"ab"
            return Transcript("chut", 0)

    runtime.policy.holo, runtime.stt = Holo(), Stt()
    _, writer = await addon(runtime)
    ws = await desktop(runtime)
    try:
        await synchronized(runtime, writer, ws)
        await permissions(ws)
        runtime.policy.level = 2
        await send_ws(ws, "capture.result", capture(runtime))
        assert (await read_ws(ws, "command"))["payload"]["type"] == "pointer"
        await send_ws(ws, "ptt.start", {"utterance_id": "u"})
        for sequence, data in [(1, b"b"), (0, b"a")]:
            await send_ws(ws, "audio.chunk", {"utterance_id": "u", "sequence": sequence,
                          "encoding": "pcm_s16le", "sample_rate": 16000,
                          "data_base64": base64.b64encode(data).decode()})
        await send_ws(ws, "ptt.stop", {"utterance_id": "u"})
        assert (await read_ws(ws, "command"))["payload"]["type"] == "stop"
        assert runtime.policy.muted
    finally:
        await ws.close()
        writer.close()


async def test_native_pointer_rejection_falls_back_only_for_current_generation(runtime):
    runtime.policy.level = 3
    generation = runtime.session.generation
    runtime.pointer_pending["old"] = generation - 1
    payload = {"command_id": "old", "status": "rejected", "detail": "pointer_stale"}
    await runtime.desktop_message({"type": "input.result", "payload": payload}, None)
    assert runtime.policy.level == 3
    runtime.pointer_pending["current"] = generation
    payload = {**payload, "command_id": "current"}
    await runtime.desktop_message({"type": "input.result", "payload": payload}, None)
    assert runtime.policy.level == 2
    assert runtime.capture is None
    assert any(e.get("kind") == "point_rejected" for e in runtime.debug.events)


async def test_debug_http_ws_metrics_and_redaction(runtime):
    base = f"http://127.0.0.1:{runtime.debug.port}"
    async with httpx.AsyncClient() as client:
        page = await client.get(base)
        assert page.status_code == 200 and "Diagnostic du moteur" in page.text
        runtime.debug.record({"kind": "status", "status": "READY"})
        runtime.debug.record({"kind": "latency", "service": "holo", "latency_ms": 12,
                              "image_png": b"private", "consent_token": "private-token"})
        metrics = (await client.get(base + "/metrics")).json()
        assert metrics["holo"] == {"count": 1, "p50": 12, "p95": 12, "max": 12}
    async with connect(base.replace("http:", "ws:") + "/ws") as ws:
        async with asyncio.timeout(1):
            while True:
                raw = await ws.recv()
                assert "private" not in raw
                event = json.loads(raw)
                if event.get("kind") == "latency" and event.get("service") == "holo":
                    assert event["latency_ms"] == 12
                    break


@pytest.mark.parametrize("shutdown", ["signal", "stdin"])
async def test_sidecar_subprocess(tmp_path, shutdown):
    env = {**os.environ, "ENGINE_SESSION_TOKEN": "subprocess-test", "ENGINE_SESSION_ID": "s1",
           "ENGINE_LEARNER_PATH": str(tmp_path / "learner.json")}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "engine", cwd=ROOT, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        line = (await asyncio.wait_for(process.stdout.readline(), 5)).decode()
        assert line.startswith("ENGINE_READY ") and line.endswith("\n")
        ports = json.loads(line.removeprefix("ENGINE_READY "))
        assert set(ports) == {"ws_port", "addon_port"}
        reader, writer = await asyncio.open_connection("127.0.0.1", ports["addon_port"])
        await send_event(writer, event())
        assert (await read_command(reader))["type"] == "request_snapshot"
        async with connect(f"ws://127.0.0.1:{ports['ws_port']}?token=subprocess-test") as ws:
            await send_ws(ws, "hello", {"app_version": "1", "platform": "linux",
                                       "capabilities": []})
            assert (await read_ws(ws))["type"] == "lesson.state"
        writer.close()
        started = time.perf_counter()
        if shutdown == "signal":
            process.send_signal(signal.SIGTERM)
        else:
            process.stdin.write(b"shutdown\n")
            await process.stdin.drain()
        stdout, stderr = await asyncio.wait_for(process.communicate(), 3)
        assert process.returncode == 0, stderr.decode()
        assert time.perf_counter() - started < 3
        assert stdout == b""
        assert (tmp_path / "learner.json").exists()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def test_capture_truncation_and_correlator_empty(runtime):
    assert decode_capture(capture(runtime)) == png()
    payload = capture(runtime)
    payload["crop"]["width"] = 2
    with pytest.raises(ValueError):
        decode_capture(payload)
    assert Correlator().pending == {}


async def test_runtime_timer_success_and_memory(runtime):
    _, writer = await addon(runtime)
    ws = await desktop(runtime)
    try:
        await synchronized(runtime, writer, ws)
        runtime.clock.advance(20)
        # Le timer de fond, sans heartbeat add-on, déclenche l'aide.
        assert (await read_ws(ws, "command"))["payload"]["type"] == "say"
        assert runtime.policy.level == 1
        await send_event(writer, event("scene.changed", 3, 1, changed_ids=["torus"], objects=[{
            "id": "torus", "type": "MESH", "primitive_provenance": "torus",
                       "mesh": {"verts": 576, "edges": 1152, "polys": 576},
        }]))
        command = (await read_ws(ws, "command"))["payload"]
        assert command["type"] == "success"
        async with asyncio.timeout(1):
            while runtime.session.status != "COMPLETE":
                await asyncio.sleep(0)
        skill = runtime.learner.skills[runtime.session.step["skill_id"]]
        assert skill.max_help_level_used == 1 and not skill.unlocked
        assert runtime.config.learner_path.exists()
        assert "check→decision" in runtime.debug.metrics()
        assert "decision→send" in runtime.debug.metrics()
    finally:
        await ws.close()
        writer.close()


async def test_runtime_demo_ack_before_undo(runtime):
    reader, writer = await addon(runtime)
    ws = await desktop(runtime)
    try:
        await synchronized(runtime, writer, ws)
        runtime.policy.level = 3
        await send_ws(ws, "user.intent", {"text": "aide", "source": "bouton"})
        replay = await read_command(reader)
        assert replay["type"] == "replay"
        assert runtime.policy.demo_checkpoint == "safe-cp"
        # Aucune commande undo n'est encore envoyée.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(reader.readline(), 0.01)
        await send_event(writer, event("command.result", 3, command_id=replay["command_id"],
                                      status="ok", detail="Démo terminée", scene_revision=0))
        undo = await read_command(reader)
        assert undo["type"] == "undo_demo" and undo["payload"]["checkpoint_id"] == "safe-cp"
    finally:
        await ws.close()
        writer.close()


async def test_audio_missing_service_overflow_and_incomplete(runtime):
    ws = await desktop(runtime)
    try:
        await permissions(ws)
        await send_ws(ws, "ptt.start", {"utterance_id": "u"})
        await send_ws(ws, "audio.chunk", {"utterance_id": "u", "sequence": 0,
                      "encoding": "pcm_s16le", "sample_rate": 16000, "data_base64": "YQ=="})
        await send_ws(ws, "ptt.stop", {"utterance_id": "u"})
        assert (await read_ws(ws, "error"))["payload"]["code"] == "stt_unavailable"
        await send_ws(ws, "ptt.start", {"utterance_id": "v"})
        await send_ws(ws, "ptt.stop", {"utterance_id": "v"})
        assert (await read_ws(ws, "error"))["payload"]["code"] == "invalid_message"
        await send_ws(ws, "ptt.start", {"utterance_id": "w"})
        await send_ws(ws, "audio.chunk", {"utterance_id": "w", "sequence": 2048,
                      "encoding": "pcm_s16le", "sample_rate": 16000, "data_base64": "YQ=="})
        assert (await read_ws(ws, "error"))["payload"]["code"] == "audio_overflow"
    finally:
        await ws.close()


async def test_unlocked_consent_and_wrong_source(runtime):
    _, writer = await addon(runtime)
    ws = await desktop(runtime)
    try:
        await synchronized(runtime, writer, ws)
        runtime.learner.review(runtime.session.step["skill_id"], passed=True, help_level=0,
                               challenge=True)
        await send_ws(ws, "user.intent", {"source": "clavier", "text": json.dumps({
            "intent": "fais-le", "consent_token": str(uuid4()),
        })})
        assert (await read_ws(ws, "error"))["payload"]["code"] == "consent_required"
        await consent(ws)
        assert (await read_ws(ws, "lesson.state"))["payload"]["status"] == "ACTING"
    finally:
        await ws.close()
        writer.close()


async def test_next_target_preload_off_critical_path(runtime):
    started, release = asyncio.Event(), asyncio.Event()

    class Holo:
        async def localize(self, image_png, description, *, timeout_s):
            assert description == "Cible suivante"
            started.set()
            await release.wait()
            return LocalizeResult(10, 20, None, 0, True)

        async def verify_point(self, *args, **kwargs):
            return True

    following = deepcopy(runtime.session.step)
    following["id"] = "second"
    following["target"]["description"] = "Cible suivante"
    runtime.session.lesson["steps"].append(following)
    runtime.policy.holo = Holo()
    ws = await desktop(runtime)
    try:
        await permissions(ws)
        await send_ws(ws, "capture.result", capture(runtime))
        await asyncio.wait_for(started.wait(), 1)
        await send_ws(ws, "ping", {"nonce": "not-blocked"})
        assert (await read_ws(ws, "pong"))["payload"]["nonce"] == "not-blocked"
        release.set()
        await runtime.preloader.task
        assert next(iter(runtime.targets.entries.values())).context.target == "Cible suivante"
    finally:
        await ws.close()
