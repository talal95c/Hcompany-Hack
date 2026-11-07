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
from engine.services.adapters import build_clients


async def warm_up_jev(clients: dict) -> None:
    jev = clients.get("jev")
    if jev is not None:
        try:
            await jev.client.warm_up()
        except Exception:
            logging.getLogger(__name__).debug("Préchauffage Jev indisponible")


async def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    config = EngineConfig.from_env()
    clients = build_clients(config)
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
    warm_up = asyncio.create_task(warm_up_jev(clients))
    try:
        await runtime.start()
        print("ENGINE_READY " + json.dumps({"ws_port": runtime.desktop.port,
                                           "addon_port": runtime.addon.port}), flush=True)
        await stopped.wait()
    finally:
        warm_up.cancel()
        await asyncio.gather(warm_up, return_exceptions=True)
        await asyncio.wait_for(runtime.close(), 2.5)
        await asyncio.gather(*(client.aclose() for client in clients.values()))


if __name__ == "__main__":
    asyncio.run(main())
