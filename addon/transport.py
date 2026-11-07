"""Socket asyncio isolé de bpy, avec contre-pression et reconnexion."""

import asyncio
import json
import queue
import threading
import time
from collections import deque
from typing import Any

MAX_LINE = 1024 * 1024


class Transport:
    def __init__(self, port: int) -> None:
        if not 0 < port < 65536:
            raise ValueError("Port local invalide")
        self.port = port
        self.incoming: queue.Queue[tuple[float, dict[str, Any]]] = queue.Queue(256)
        self.outgoing: queue.Queue[dict[str, Any]] = queue.Queue(256)
        self.connected = threading.Event()
        self.ready = threading.Event()
        self.generation = 0
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="addon-socket")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.closed.set()
        self.thread.join(timeout=3)

    def _run(self) -> None:
        asyncio.run(self._connect())

    async def _connect(self) -> None:
        delay = 0.1
        while not self.closed.is_set():
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self.port, limit=MAX_LINE), 2
                )
                self.ready.clear()
                self.generation += 1
                self.connected.set()
                delay = 0.1
                await self._exchange(reader, writer)
            except (TimeoutError, OSError, ValueError):
                pass
            finally:
                self.connected.clear()
                if writer is not None:
                    writer.close()
                    try:
                        await asyncio.wait_for(writer.wait_closed(), 0.5)
                    except (OSError, TimeoutError):
                        pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, 2)

    async def _exchange(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        pending: deque[tuple[float, dict[str, Any]]] = deque()
        read = asyncio.create_task(reader.readline())
        try:
            while not self.closed.is_set():
                if not self.ready.is_set():
                    await asyncio.sleep(0.002)
                    continue
                if read.done():
                    line = read.result()
                    if not line:
                        return
                    try:
                        value = json.loads(line)
                        if isinstance(value, dict):
                            pending.append((time.monotonic(), value))
                    except (ValueError, UnicodeError):
                        pass
                    read = asyncio.create_task(reader.readline())
                if pending and not self.incoming.full():
                    self.incoming.put_nowait(pending.popleft())
                if not self.outgoing.empty():
                    event = self.outgoing.get_nowait()
                    writer.write(json.dumps(event, allow_nan=False).encode() + b"\n")
                    await asyncio.wait_for(writer.drain(), 1)
                if len(pending) >= 256:
                    raise ValueError("Trop de commandes en attente")
                await asyncio.sleep(0.002)
        finally:
            read.cancel()
            await asyncio.gather(read, return_exceptions=True)
