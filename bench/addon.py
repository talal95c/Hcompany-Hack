"""Local JSON-lines probe, independent of the production add-on and engine."""

import asyncio
import json
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from bench.common import ROOT, Timer, statistics


class Listener:
    def __init__(self, session: str, timeout: float = 30) -> None:
        self.session = session
        self.timeout = timeout
        self.events: list[dict[str, Any]] = []
        self.commands: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.invalid_events = 0
        self.invalid_commands = 0
        self.empty_lines = 0
        self.rtts: list[float] = []
        self.pending: dict[str, float] = {}
        self.startup: float | None = None
        self.timer = Timer()
        self.done = asyncio.Event()
        self.tasks: set[asyncio.Task] = set()
        self.validators = {
            name: Draft202012Validator(
                json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text())
            )
            for name in ("addon-events", "commands")
        }

    def connected(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self.handle(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), self.timeout)
                received_ms = time.monotonic() * 1000
                received_perf = time.perf_counter()
                if not line:
                    break
                if not line.strip():
                    self.empty_lines += 1
                    continue
                try:
                    event = json.loads(line)
                    self.validators["addon-events"].validate(event)
                except (ValueError, UnicodeDecodeError, ValidationError):
                    self.invalid_events += 1
                    continue
                if event["session_id"] != self.session:
                    self.invalid_events += 1
                    continue
                self.events.append(
                    {
                        "event": event,
                        "received_monotonic_ms": received_ms,
                        "latency_ms": received_ms - event["ts_monotonic_ms"],
                    }
                )
                if event["type"] == "hello" and self.startup is None:
                    self.startup = (received_perf - self.timer.started) * 1000
                if event["type"] == "heartbeat":
                    await self.send_command(writer, event["scene_revision"])
                elif event["type"] == "command.result":
                    command_id = event["payload"]["command_id"]
                    if command_id in self.pending:
                        self.rtts.append((received_perf - self.pending.pop(command_id)) * 1000)
                    else:
                        self.errors.append("Unmatched command.result")
        except (TimeoutError, ConnectionError, ValueError) as exc:
            self.errors.append(type(exc).__name__)
        finally:
            writer.close()
            await writer.wait_closed()
            self.done.set()

    async def send_command(self, writer: asyncio.StreamWriter, revision: int) -> None:
        command = {
            "schema_version": "1.0",
            "session_id": self.session,
            "command_id": str(uuid.uuid4()),
            "step_id": None,
            "generation": 0,
            "recipient": "addon",
            "type": "request_snapshot",
            "deadline_ms": 5000,
            "expected_scene_revision": revision,
            "payload": {},
        }
        try:
            self.validators["commands"].validate(command)
        except ValidationError:
            self.invalid_commands += 1
            raise
        self.pending[command["command_id"]] = time.perf_counter()
        self.commands.append(command)
        writer.write(json.dumps(command).encode() + b"\n")
        await writer.drain()


async def run(
    *, operations: int = 50, blender: str = "/opt/blender/blender", timeout: float = 60
) -> dict[str, Any]:
    if operations < 1 or timeout <= 0:
        raise ValueError("operations and timeout must be positive")
    listener = Listener(str(uuid.uuid4()), timeout)
    server = await asyncio.start_server(listener.connected, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    process = None
    listener.timer = Timer()
    try:
        process = await asyncio.create_subprocess_exec(
            blender,
            "-b",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).parent / "blender" / "probe.py"),
            "--",
            "--port",
            str(port),
            "--session",
            listener.session,
            "--operations",
            str(operations),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise RuntimeError(f"Blender exited {process.returncode}: {output.decode()[-3000:]}")
        await asyncio.wait_for(listener.done.wait(), timeout)
    finally:
        server.close()
        await server.wait_closed()
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        for task in list(listener.tasks):
            task.cancel()
        await asyncio.gather(*listener.tasks, return_exceptions=True)
    groups: dict[str, list[float]] = defaultdict(list)
    for sample in listener.events:
        groups[sample["event"]["type"]].append(sample["latency_ms"])
    expected = {
        "hello": 1,
        "snapshot": operations + 1,
        "operator.executed": operations,
        "scene.changed": operations,
        "heartbeat": operations,
        "command.result": operations,
    }
    counts = {key: len(values) for key, values in groups.items()}
    if counts != expected or listener.pending or listener.errors:
        raise RuntimeError(f"Incomplete probe: counts={counts}, errors={listener.errors}")
    return {
        "summary": {
            "startup_to_hello_ms": listener.startup,
            "one_way": {key: statistics(v) for key, v in groups.items()},
            "rtt": statistics(listener.rtts),
            "counts": counts,
            "invalid_events": listener.invalid_events,
            "invalid_commands": listener.invalid_commands,
        },
        "blender_version": listener.events[0]["event"]["payload"]["blender_version"],
        "configuration": {"operations": operations, "blender": blender},
        "notes": [
            "Sonde autonome, pas le véritable add-on ni le moteur de production.",
            "Linux : CLOCK_MONOTONIC partagé entre processus sur le même hôte ; "
            "aucune comparaison inter-hôtes. Réception horodatée avant validation.",
            "Percentiles nearest-rank ; aucune latence simulée. "
            "RTT = request_snapshot → snapshot puis command.result.",
            "Événements émis directement après chaque opération bpy réelle ; "
            "ces mesures excluent les observateurs du véritable add-on.",
        ],
        "raw_samples": listener.events,
        "sent_commands": listener.commands,
        "rtt_samples_ms": listener.rtts,
        "errors": listener.errors,
    }
