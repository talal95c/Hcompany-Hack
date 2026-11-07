import asyncio
import json
import os
import shutil
import signal
import sysconfig
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live
@pytest.mark.blender
async def test_graphical_blender_real_timers(tmp_path: Path) -> None:
    binary = shutil.which("blender")
    xvfb = shutil.which("xvfb-run")
    if not binary or not xvfb or not shutil.which("Xvfb"):
        pytest.skip("Graphical Blender requires Blender, Xvfb and xvfb-run")
    validators = {
        name: Draft202012Validator(
            json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text())
        )
        for name in ("commands", "addon-events")
    }
    connections = asyncio.Queue()

    async def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await connections.put((reader, writer))

    server = await asyncio.start_server(connected, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    session = uuid.uuid4().hex
    process = await asyncio.create_subprocess_exec(
        xvfb,
        "-a",
        "-s",
        "-screen 0 1280x900x24",
        binary,
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).with_name("graphical_harness.py")),
        env=dict(
            os.environ,
            LIBGL_ALWAYS_SOFTWARE="1",
            XDG_RUNTIME_DIR=str(tmp_path),
            ADDON_ENGINE_PORT=str(port),
            ADDON_SESSION_TOKEN=session,
            ADDON_TEST_SITE=sysconfig.get_path("purelib"),
        ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    output_task = asyncio.create_task(process.communicate())
    events: list[tuple[float, dict[str, Any]]] = []
    latencies: list[float] = []
    writer = None
    try:
        reader, writer = await asyncio.wait_for(connections.get(), 30)
        sequence = 0

        async def receive(kind: str, identifier: str | None = None) -> dict[str, Any]:
            nonlocal sequence
            async with asyncio.timeout(15):
                while True:
                    line = await reader.readline()
                    assert line, "Graphical Blender disconnected"
                    event = json.loads(line)
                    validators["addon-events"].validate(event)
                    assert event["session_id"] == session
                    assert event["seq"] > sequence
                    sequence = event["seq"]
                    events.append((time.monotonic() * 1000, event))
                    if event["type"] == kind and (
                        identifier is None or event["payload"].get("command_id") == identifier
                    ):
                        return event

        async def send(
            kind: str,
            payload: dict[str, Any],
            identifier: str | None = None,
            revision: int | None = None,
        ) -> dict[str, Any]:
            command = {
                "schema_version": "1.0",
                "session_id": session,
                "command_id": identifier or uuid.uuid4().hex,
                "step_id": None,
                "generation": 0,
                "recipient": "addon",
                "type": kind,
                "deadline_ms": 10000,
                "expected_scene_revision": revision,
                "payload": payload,
            }
            validators["commands"].validate(command)
            before = time.monotonic() * 1000
            writer.write(json.dumps(command).encode() + b"\n")
            await writer.drain()
            event = await receive("command.result", command["command_id"])
            latencies.append(time.monotonic() * 1000 - before)
            return event["payload"]

        hello = await receive("hello")
        assert hello["seq"] == 1
        initial_regions = await receive("regions.changed")
        assert initial_regions["payload"]["regions"]
        await receive("snapshot")
        result = await send("replay", {"procedure_ref": "add_cube", "params": {"size": 10**400}})
        assert result["status"] == "rejected", result
        assert result["error_code"] == "bad_context"
        first = await receive("heartbeat")
        second = await receive("heartbeat")
        assert second["payload"]["uptime_ms"] > first["payload"]["uptime_ms"]
        assert (await send("request_snapshot", {}))["status"] == "ok"
        assert (await send("request_snapshot", {}, "measure_action"))["status"] == "ok"
        await receive("scene.changed")

        server.close()
        await server.wait_closed()
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.3)
        server = await asyncio.start_server(connected, "127.0.0.1", port)
        reader, writer = await asyncio.wait_for(connections.get(), 10)
        sequence = 0
        assert (await receive("hello"))["seq"] == 1
        regions = await receive("regions.changed")
        assert regions["payload"]["ui_revision"] > initial_regions["payload"]["ui_revision"]
        assert regions["payload"]["regions"] == initial_regions["payload"]["regions"]
        assert all(r["area_id"] and r["region_id"] for r in regions["payload"]["regions"])
        state = await receive("snapshot")
        fixture = json.loads((ROOT / "contracts/examples/commands/valid/replay.json").read_text())
        result = await send(fixture["type"], fixture["payload"], revision=state["scene_revision"])
        assert result["status"] == "ok", result
        assert (await send("request_snapshot", {}))["status"] == "ok"
        state = next(e for _, e in reversed(events) if e["type"] == "snapshot")
        assert any(o.get("primitive_provenance") == "torus" for o in state["payload"]["objects"])
        menu = json.loads((ROOT / "contracts/examples/commands/valid/open_menu.json").read_text())
        menu_results = []
        for region in regions["payload"]["regions"]:
            if region["type"] != "WINDOW":
                continue
            result = await send(
                "open_menu",
                {
                    **menu["payload"],
                    "area_id": region["area_id"],
                    "region_id": region["region_id"],
                },
            )
            menu_results.append(result)
            if result["status"] == "ok":
                break
        assert any(r["status"] == "ok" for r in menu_results), menu_results
        assert (await send("request_snapshot", {}, "finish"))["status"] == "ok"
        output, _ = await asyncio.wait_for(asyncio.shield(output_task), 15)
        assert process.returncode == 0, output.decode()
        action = next(
            json.loads(line.removeprefix("ACTION "))
            for line in output.decode().splitlines()
            if line.startswith("ACTION ")
        )
        received = next(
            received
            for received, event in events
            if event["type"] == "scene.changed" and event["ts_monotonic_ms"] >= action["started_ms"]
        )
        print(f"Graphical Blender: {len(events)} schema-valid events, {len(latencies)} commands")
        print(f"Real timer action → scene.changed ms: {received - action['started_ms']:.2f}")
        print(
            f"Real timer command → result ms: min={min(latencies):.2f}, "
            f"mean={sum(latencies) / len(latencies):.2f}, max={max(latencies):.2f}"
        )
    finally:
        if writer:
            writer.close()
        server.close()
        await server.wait_closed()
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
        output, _ = await output_task
        if process.returncode:
            print(output.decode())
