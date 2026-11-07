"""Session graphique privée et protocole JSON pour les suites locales."""

import asyncio
import json
import math
import os
import signal
import tempfile
from pathlib import Path
from typing import Any

from bench.common import ROOT


def parse_response(line: bytes) -> dict[str, Any]:
    try:
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError
        if "error" in response:
            raise RuntimeError(response["error"])
        value = response["latency_ms"]
        if (
            "result" not in response
            or type(value) not in (int, float)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError
        return response
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("Réponse AT-SPI invalide") from error


class A11ySession:
    def __init__(
        self, timeout: float = 15, plugin: str = "gtk3", startup_timeout: float = 65
    ) -> None:
        self.timeout = timeout
        self.plugin = plugin
        self.startup_timeout = startup_timeout
        self.process: asyncio.subprocess.Process | None = None
        self.runtime: tempfile.TemporaryDirectory | None = None
        self.broken = False

    async def __aenter__(self) -> "A11ySession":
        self.runtime = tempfile.TemporaryDirectory(prefix="bench-a11y-")
        os.chmod(self.runtime.name, 0o700)
        env = {**os.environ, "XDG_RUNTIME_DIR": self.runtime.name}
        for key in ("DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS"):
            env.pop(key, None)
        try:
            self.process = await asyncio.create_subprocess_exec(
                "dbus-run-session",
                "--",
                "/usr/bin/python3",
                str(Path(__file__).with_name("a11y_probe.py")),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=ROOT,
                env=env,
                start_new_session=True,
            )
            return self
        except BaseException:
            await self.close()
            raise

    async def request(self, op: str, **arguments: Any) -> dict[str, Any]:
        if self.broken or self.process is None or self.process.returncode is not None:
            raise RuntimeError("Session AT-SPI arrêtée")
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps({"op": op, "arguments": arguments}).encode() + b"\n")
        await self.process.stdin.drain()
        limit = self.startup_timeout if op == "start" else self.timeout
        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), limit)
        except TimeoutError:
            self.broken = True
            raise
        if not line:
            raise RuntimeError("Sonde AT-SPI déconnectée")
        return parse_response(line)

    async def launch_calc(self) -> dict[str, Any]:
        return (await self.request("start", plugin=self.plugin, timeout=self.startup_timeout - 5))[
            "result"
        ]

    async def find_element(self, name: str) -> dict[str, Any] | None:
        return (await self.request("find", name=name))["result"]

    async def close(self) -> None:
        if self.process is not None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(self.process.wait(), 5)
                except TimeoutError:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    await self.process.wait()
            self.process = None
        if self.runtime is not None:
            self.runtime.cleanup()
            self.runtime = None

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
