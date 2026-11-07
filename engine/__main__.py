"""Point d'entrée sidecar ; stdout réservé au handshake de disponibilité."""

import asyncio
import json
import logging
import os
import signal
import sys
import threading

from engine.config import EngineConfig
from engine.lesson.runtime import EngineRuntime


async def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    config = EngineConfig.from_env()
    clients = {}
    try:
        from engine.services import build_clients

        clients = build_clients(config)
    except ImportError:
        pass
    runtime = EngineRuntime(config, **(clients or {}))
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, stopped.set)
        except NotImplementedError:
            signal.signal(name, lambda *_: loop.call_soon_threadsafe(stopped.set))

    def stdin() -> None:
        pending = b""
        while True:
            data = os.read(0, 1024)
            if not data:
                return
            pending += data
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line.strip() == b"shutdown":
                    loop.call_soon_threadsafe(stopped.set)
                    return
            if len(pending) > 4096:
                pending = b""

    threading.Thread(target=stdin, daemon=True).start()
    try:
        await runtime.start()
        print("ENGINE_READY " + json.dumps({"ws_port": runtime.desktop.port,
                                           "addon_port": runtime.addon.port}), flush=True)
        await stopped.wait()
    finally:
        await asyncio.wait_for(runtime.close(), 2.5)


if __name__ == "__main__":
    asyncio.run(main())
