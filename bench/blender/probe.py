"""Executed by Blender's Python, using only bpy and the standard library."""

import argparse
import json
import socket
import sys
import time
from typing import Any

import bpy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--operations", type=int, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    started = time.monotonic()
    seq = 0
    revision = 0
    with socket.create_connection(("127.0.0.1", args.port), timeout=30) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        stream = connection.makefile("rb")

        def emit(kind: str, payload: dict[str, Any]) -> None:
            nonlocal seq
            event = {
                "schema_version": "1.0",
                "session_id": args.session,
                "event_id": f"probe-{seq}",
                "seq": seq,
                "ts_monotonic_ms": time.monotonic() * 1000,
                "scene_revision": revision,
                "type": kind,
                "payload": payload,
            }
            seq += 1
            connection.sendall(json.dumps(event).encode() + b"\n")

        def snapshot() -> None:
            emit(
                "snapshot",
                {
                    "mode": bpy.context.mode,
                    "active": bpy.context.object.name if bpy.context.object else None,
                    "objects": [
                        {"name": obj.name, "location": list(obj.location)}
                        for obj in bpy.context.scene.objects
                    ],
                },
            )

        emit(
            "hello",
            {"blender_version": bpy.app.version_string, "capabilities": ["request_snapshot"]},
        )
        snapshot()
        for index in range(args.operations):
            bpy.ops.mesh.primitive_cube_add(location=(index * 2, 0, 0))
            revision += 1
            emit(
                "operator.executed",
                {
                    "idname": "MESH_OT_primitive_cube_add",
                    "properties": {"location": [index * 2, 0, 0]},
                },
            )
            obj = bpy.context.object
            emit(
                "scene.changed",
                {
                    "changed_ids": [obj.name],
                    "objects": [{"name": obj.name, "location": list(obj.location)}],
                },
            )
            emit("heartbeat", {"uptime_ms": (time.monotonic() - started) * 1000})
            command = json.loads(stream.readline())
            if command["type"] != "request_snapshot" or command["session_id"] != args.session:
                raise ValueError("Unexpected command")
            snapshot()
            emit(
                "command.result",
                {
                    "command_id": command["command_id"],
                    "status": "ok",
                    "detail": "snapshot sent",
                    "scene_revision": revision,
                },
            )
        stream.close()


if __name__ == "__main__":
    main()
