"""Tiny authenticated protocol fixture for native UI tests, not a product engine."""

import argparse
import asyncio
import base64
import hmac
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from websockets.asyncio.server import serve

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = [json.loads(p.read_text()) for p in (ROOT / "contracts").glob("*.schema.json")]
REGISTRY = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in SCHEMAS)
VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "contracts/desktop-ws.schema.json").read_text()), registry=REGISTRY
)


async def main(port: int, output: Path, sidecar: bool = False) -> None:
    token = os.environ["ENGINE_SESSION_TOKEN"]
    session = os.environ["ENGINE_SESSION_ID"]
    output.mkdir(parents=True, exist_ok=True)

    def event(kind: str, **details) -> None:
        with (output / "probe.jsonl").open("a") as file:
            file.write(json.dumps({"event": kind, **details}) + "\n")

    def envelope(kind: str, payload: dict) -> dict:
        value = {
            "schema_version": "1.0",
            "session_id": session,
            "message_id": str(uuid.uuid4()),
            "reply_to": None,
            "type": kind,
            "payload": payload,
        }
        VALIDATOR.validate(value)
        return value

    def command(kind: str, payload: dict, revision: int | None = None) -> dict:
        return envelope(
            "command",
            {
                "schema_version": "1.0",
                "session_id": session,
                "command_id": str(uuid.uuid4()),
                "step_id": "protocol-probe",
                "generation": 1,
                "recipient": "desktop",
                "type": kind,
                "deadline_ms": 5000,
                "expected_scene_revision": revision,
                "payload": payload,
            },
        )

    async def authenticate(connection, request):
        if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
            return connection.respond(401, "Unauthorized")
        if request.headers.get("Origin") != "tauri://localhost":
            return connection.respond(403, "Forbidden")
        return None

    async def handler(socket):
        event("connected")
        async for raw in socket:
            packet = json.loads(raw)
            VALIDATOR.validate(packet)
            assert packet["session_id"] == session
            kind, payload = packet["type"], packet["payload"]
            event(kind, **({"status": payload["status"]} if kind == "input.result" else {}))
            if kind == "hello":
                await socket.send(
                    json.dumps(
                        envelope(
                            "lesson.state",
                            {
                                "step_id": "protocol-probe",
                                "status": "OBSERVING",
                                "instruction": "Test du transport natif — partagez une région.",
                                "help_level": 3,
                            },
                        )
                    )
                )
                await socket.send('{"type":"command","payload":{}}')
                event("invalid_fixture_sent")
            elif kind == "capture.result":
                start = time.perf_counter()
                prefix, image = payload["image_ref"].split(",", 1)
                assert prefix == "data:image/png;base64"
                (output / "native-crop.png").write_bytes(base64.b64decode(image, validate=True))
                await socket.send(
                    json.dumps(
                        command(
                            "pointer",
                            {
                                "capture_id": payload["capture_id"],
                                "ui_revision": payload["ui_revision"],
                                "x": 500,
                                "y": 500,
                            },
                        )
                    )
                )
                await socket.send(
                    json.dumps(
                        command(
                            "input.action",
                            {
                                "capture_id": payload["capture_id"],
                                "consent_token": "invalid-fixture-token",
                                "action": {"type": "click", "x": 500, "y": 500, "button": "left"},
                            },
                        )
                    )
                )
                event(
                    "pointer_sent",
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                    crop=payload["crop"],
                    ui_revision=payload["ui_revision"],
                )
            elif kind == "user.intent" and payload["text"] == "stop":
                await socket.send(json.dumps(command("stop", {"reason": "user stop"})))
            elif kind == "user.intent" and payload["text"] == "probe-success":
                await socket.send(
                    json.dumps(
                        command(
                            "success",
                            {
                                "text": "Test du rendu vérifié — fixture de protocole uniquement.",
                            },
                            revision=1,
                        )
                    )
                )
                event("success_sent")
            elif kind == "ping":
                await socket.send(json.dumps(envelope("pong", payload)))

    async with serve(
        handler, "127.0.0.1", port, process_request=authenticate, max_size=8 * 1024**2
    ):
        if not sidecar:
            print(f"PROBE_READY {port}", flush=True)
            await asyncio.Future()
        else:
            stopped = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, stopped.set)
            reader = asyncio.StreamReader()
            await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

            async def read_shutdown():
                while await reader.readline() not in (b"", b"shutdown\n"):
                    pass
                stopped.set()

            shutdown = asyncio.create_task(read_shutdown())
            print("ENGINE_READY " + json.dumps({"ws_port": port}), flush=True)
            event("sidecar_ready")
            await stopped.wait()
            event("sidecar_stopped")
            shutdown.cancel()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sidecar", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.port, args.output, args.sidecar))
