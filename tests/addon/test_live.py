import asyncio
import json
import os
import shutil
import sysconfig
import time
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live
@pytest.mark.blender
async def test_real_blender_socket_stream(tmp_path):
    binary = shutil.which("blender")
    if not binary:
        pytest.skip("Blender absent")
    validators = {
        name: Draft202012Validator(
            json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text())
        )
        for name in ("addon-events", "commands")
    }
    connections = asyncio.Queue()

    async def connected(reader, writer):
        await connections.put((reader, writer))

    server = await asyncio.start_server(connected, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    session = uuid.uuid4().hex
    env = dict(
        os.environ,
        ADDON_ENGINE_PORT=str(port),
        ADDON_SESSION_TOKEN=session,
        ADDON_TEST_SITE=sysconfig.get_path("purelib"),
        ADDON_TEST_FILE=str(tmp_path / "roundtrip.blend"),
    )
    process = await asyncio.create_subprocess_exec(
        binary,
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).with_name("harness.py")),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    events = []
    latencies = []
    writer = None
    try:
        reader, writer = await asyncio.wait_for(connections.get(), 15)
        sequence = 0

        async def receive(predicate):
            nonlocal sequence
            async with asyncio.timeout(10):
                while True:
                    line = await reader.readline()
                    assert line, "Connexion fermée"
                    event = json.loads(line)
                    validators["addon-events"].validate(event)
                    assert event["session_id"] == session
                    assert event["seq"] > sequence
                    sequence = event["seq"]
                    events.append((time.monotonic() * 1000, event))
                    if predicate(event):
                        return event

        async def send(kind, payload=None, identifier=None, **overrides):
            command = {
                "schema_version": "1.0",
                "session_id": session,
                "command_id": identifier or uuid.uuid4().hex,
                "step_id": None,
                "generation": 0,
                "recipient": "addon",
                "type": kind,
                "deadline_ms": 3000,
                "expected_scene_revision": None,
                "payload": payload or {},
                **overrides,
            }
            validators["commands"].validate(command)
            before = time.monotonic() * 1000
            writer.write(json.dumps(command).encode() + b"\n")
            await writer.drain()
            result = await receive(
                lambda e: (
                    e["type"] == "command.result"
                    and e["payload"]["command_id"] == command["command_id"]
                )
            )
            latencies.append(time.monotonic() * 1000 - before)
            return result["payload"]

        assert (await receive(lambda e: True))["type"] == "hello"
        initial = await receive(lambda e: e["type"] == "snapshot")
        assert initial["payload"]["objects"] == []
        await receive(
            lambda e: e["type"] == "mode.changed" and e["payload"]["current"] == "EDIT_MESH"
        )
        await receive(lambda e: e["type"] == "mode.changed" and e["payload"]["current"] == "OBJECT")
        assert (await send("request_snapshot"))["status"] == "ok"
        state = next(e for _, e in reversed(events) if e["type"] == "snapshot")
        objects = state["payload"]["objects"]
        assert len(objects) == 2
        assert any(o.get("mesh", {}).get("verts") == 576 for o in objects)
        assert any(m["type"] == "SUBSURF" for o in objects for m in o["modifiers"])
        direct_count = len(objects)
        for name in ("add_torus", "add_cube", "add_subdivision_modifier"):
            result = await send("replay", {"procedure_ref": name, "params": {}}, identifier=name)
            assert result["status"] == "ok", result
        assert (
            await send("replay", {"procedure_ref": "add_cube", "params": {}}, identifier="add_cube")
        )["status"] == "ok"
        assert (await send("request_snapshot"))["status"] == "ok"
        state = next(e for _, e in reversed(events) if e["type"] == "snapshot")
        assert len(state["payload"]["objects"]) == direct_count + 2
        assert {o.get("primitive_provenance") for o in state["payload"]["objects"]} >= {
            "torus",
            "cube",
        }
        cases = [
            ("request_snapshot", {}, {"deadline_ms": 0}, "expired", None),
            ("request_snapshot", {}, {"expected_scene_revision": 9999}, "rejected", "stale_state"),
            (
                "replay",
                {"procedure_ref": "forbidden", "params": {}},
                {},
                "rejected",
                "unknown_procedure",
            ),
            (
                "replay",
                {"procedure_ref": "add_cube", "params": {"size": -1}},
                {},
                "rejected",
                "bad_context",
            ),
            (
                "highlight",
                {"area_id": "absent", "region_id": "absent", "color": "#ff0000", "duration_ms": 10},
                {},
                "rejected",
                "bad_context",
            ),
            (
                "open_menu",
                {"area_id": "absent", "region_id": "absent", "menu_id": "VIEW3D_MT_mesh_add"},
                {},
                "rejected",
                "bad_context",
            ),
            ("undo_demo", {"checkpoint_id": "absent"}, {}, "rejected", "stale_state"),
            ("clear_highlight", {}, {}, "ok", None),
        ]
        for kind, payload, options, status, code in cases:
            result = await send(kind, payload, **options)
            assert result["status"] == status, result
            assert result.get("error_code") == code
        result = await send("replay", {"procedure_ref": "add_cube", "params": {"size": 10**400}})
        assert result["status"] == "rejected", result
        assert result["error_code"] == "bad_context"
        assert (await send("request_snapshot"))["status"] == "ok"
        await receive(lambda e: e["type"] == "heartbeat")
        fixture = json.loads((ROOT / "contracts/examples/commands/valid/replay.json").read_text())
        state = next(e for _, e in reversed(events) if e["type"] == "snapshot")
        result = await send(
            fixture["type"],
            fixture["payload"],
            expected_scene_revision=state["scene_revision"],
        )
        assert result["status"] == "ok", result
        initial_regions = next(e for _, e in events if e["type"] == "regions.changed")
        writer.write(b"not-json\n{}\n")
        await writer.drain()
        server.close()
        await server.wait_closed()
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.2)
        server = await asyncio.start_server(connected, "127.0.0.1", port)
        reader, writer = await asyncio.wait_for(connections.get(), 5)
        sequence = 0
        assert (await receive(lambda e: True))["type"] == "hello"
        regions = await receive(lambda e: e["type"] == "regions.changed")
        assert regions["payload"]["regions"] == initial_regions["payload"]["regions"]
        assert regions["payload"]["ui_revision"] > initial_regions["payload"]["ui_revision"]
        await receive(lambda e: e["type"] == "snapshot")
        assert (
            await send("replay", {"procedure_ref": "add_cube", "params": {}}, identifier="add_cube")
        )["status"] == "ok"
        assert (await send("request_snapshot", identifier="finish"))["status"] == "ok"
        final = next(e for _, e in reversed(events) if e["type"] == "snapshot")
        assert len(final["payload"]["objects"]) == direct_count + 3
        output, _ = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode == 0, output.decode()
        actions = [
            json.loads(line.removeprefix("ACTION "))
            for line in output.decode().splitlines()
            if line.startswith("ACTION ")
        ]
        event_latencies = []
        for action in actions:
            emitted = next(
                received
                for received, e in events
                if e["type"] == "scene.changed" and e["ts_monotonic_ms"] >= action["started_ms"]
            )
            event_latencies.append(emitted - action["started_ms"])
        types = {e["type"] for _, e in events}
        assert types >= {
            "hello",
            "snapshot",
            "scene.changed",
            "selection.changed",
            "mode.changed",
            "regions.changed",
            "command.result",
            "heartbeat",
        }
        print(f"Blender live: {len(events)} événements validés, {len(latencies)} commandes")
        print("Action → scene.changed ms: " + ", ".join(f"{v:.2f}" for v in event_latencies))
        print(
            f"Commande → résultat ms: min={min(latencies):.2f}, "
            f"moyenne={sum(latencies) / len(latencies):.2f}, max={max(latencies):.2f}"
        )
        operators = [e for _, e in events if e["type"] == "operator.executed"]
        print(f"Historique REGISTER headless: {len(operators)} événements observés")
    finally:
        if writer:
            writer.close()
        server.close()
        await server.wait_closed()
        if process.returncode is None:
            process.kill()
            await process.wait()
