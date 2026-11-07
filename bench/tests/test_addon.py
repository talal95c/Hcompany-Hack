import asyncio
import json
import time

import pytest

from bench.addon import Listener, run


def event(kind: str, payload: dict) -> dict:
    return {
        "schema_version": "1.0",
        "session_id": "test",
        "event_id": "e0",
        "seq": 0,
        "ts_monotonic_ms": time.monotonic() * 1000,
        "scene_revision": 0,
        "type": kind,
        "payload": payload,
    }


async def test_listener_nominal() -> None:
    listener = Listener("test", timeout=1)
    server = await asyncio.start_server(listener.connected, "127.0.0.1", 0)
    async with server:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", server.sockets[0].getsockname()[1]
        )
        writer.write(json.dumps(event("heartbeat", {"uptime_ms": 1})).encode() + b"\n")
        await writer.drain()
        command = json.loads(await reader.readline())
        listener.validators["commands"].validate(command)
        writer.write(
            json.dumps(
                event(
                    "command.result",
                    {
                        "command_id": command["command_id"],
                        "status": "ok",
                        "detail": "done",
                        "scene_revision": 0,
                    },
                )
            ).encode()
            + b"\n"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(listener.done.wait(), 2)
    assert len(listener.events) == 2
    assert len(listener.rtts) == 1
    assert listener.rtts[0] >= 0
    assert listener.invalid_events == listener.invalid_commands == 0
    assert not listener.pending


@pytest.mark.parametrize(
    "data,invalid,empty", [(b"\n", 0, 1), (b"nope\n", 1, 0), (b"{}\n", 1, 0), (b"", 0, 0)]
)
async def test_listener_input(data: bytes, invalid: int, empty: int) -> None:
    listener = Listener("test", timeout=1)
    server = await asyncio.start_server(listener.connected, "127.0.0.1", 0)
    async with server:
        _, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        writer.write(data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(listener.done.wait(), 2)
    assert listener.invalid_events == invalid
    assert listener.empty_lines == empty
    assert listener.events == []
    assert listener.errors == []


async def test_listener_timeout() -> None:
    listener = Listener("test", timeout=0.01)
    server = await asyncio.start_server(listener.connected, "127.0.0.1", 0)
    async with server:
        _, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        await asyncio.wait_for(listener.done.wait(), 1)
        writer.close()
        await writer.wait_closed()
    assert listener.errors == ["TimeoutError"]


async def test_invalid_options() -> None:
    with pytest.raises(ValueError):
        await run(operations=0)


@pytest.mark.live
async def test_addon_live() -> None:
    report = await run(operations=50)
    summary = report["summary"]
    assert summary["invalid_events"] == summary["invalid_commands"] == 0
    assert 0 < summary["startup_to_hello_ms"] < 60000
    assert summary["rtt"]["count"] == 50
    assert 0 <= summary["rtt"]["p50_ms"] <= summary["rtt"]["p95_ms"] < 5000
    assert summary["counts"]["operator.executed"] == 50
    for sample in report["raw_samples"]:
        assert 0 <= sample["latency_ms"] < 5000
