import asyncio
import json
import time

import pytest

from addon.transport import Transport


def test_invalid_port():
    for port in (0, -1, 65536):
        with pytest.raises(ValueError):
            Transport(port)


async def test_transport_empty_invalid_and_valid_messages():
    received = asyncio.Queue()

    async def serve(reader, writer):
        writer.write(b"[]\ninvalid\n{}\n")
        await writer.drain()
        await received.put(json.loads(await reader.readline()))
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    transport = Transport(server.sockets[0].getsockname()[1])
    transport.start()
    try:
        transport.outgoing.put({"test": True})
        transport.ready.set()
        async with asyncio.timeout(5):
            while not transport.connected.is_set():
                await asyncio.sleep(0.01)
            transport.ready.set()
            assert await received.get() == {"test": True}
            while transport.incoming.empty():
                await asyncio.sleep(0.01)
            timestamp, command = transport.incoming.get_nowait()
        assert command == {}
        assert timestamp <= time.monotonic()
    finally:
        transport.stop()
        server.close()
        await server.wait_closed()
    assert not transport.thread.is_alive()
