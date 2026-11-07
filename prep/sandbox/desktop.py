"""Bac à sable de bureau générique : Xvfb, bus D-Bus et AT-SPI isolés, une application.

L'application tourne sur un écran virtuel privé ; le rejeu agit uniquement par entrées
X11 (xdotool) et lit l'état par l'arbre d'accessibilité ou par capture. Aucune clé
d'API n'est transmise aux processus du bac à sable.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import signal
import tempfile
import time
from pathlib import Path
from typing import Any

import jsonschema

from prep.apps import AppProfile

LOGGER = logging.getLogger(__name__)
WORKER = Path(__file__).with_name("atspi_worker.py")
DESKTOP_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/desktop-ws.schema.json").read_text()
)
SNAPSHOT_SCHEMA = next(
    branch["properties"]["payload"]
    for branch in DESKTOP_SCHEMA["oneOf"]
    if branch.get("properties", {}).get("type", {}).get("const") == "a11y.result"
)
WORKER_SCHEMA = {
    **SNAPSHOT_SCHEMA,
    "$defs": DESKTOP_SCHEMA["$defs"],
    "properties": {
        **{
            k: v
            for k, v in SNAPSHOT_SCHEMA["properties"].items()
            if k not in {"request_id", "snapshot_id"}
        },
        "windows": {"type": "array", "items": {"type": "string"}},
        "managed_refs": {"type": "array", "items": {"type": "string"}},
        "apps": {"type": "array", "items": {"type": "string"}},
        "duration": {"type": "number", "minimum": 0},
        "stale_skipped": {"type": "integer", "minimum": 0},
    },
    "required": ["complete", "nodes", "windows"],
    "else": {},
}
CHILD_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "DISPLAY",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_NUMERIC",
        "LC_TIME",
        "LC_COLLATE",
        "LC_MONETARY",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_DIRS",
        "XDG_CONFIG_DIRS",
        "DBUS_SESSION_BUS_ADDRESS",
        "AT_SPI_BUS_ADDRESS",
        "AT_SPI_BUS",
        "GTK_MODULES",
        "SAL_USE_VCLPLUGIN",
        "NO_AT_BRIDGE",
        "TMPDIR",
        "TMP",
        "TEMP",
        "TZ",
        "XAUTHORITY",
    }
)
KEYSYMS = {
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "cmd": "super",
    "enter": "Return",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "minus": "minus",
    "plus": "plus",
    "numpad_period": "KP_Decimal",
}


def xdotool_chord(keys: list[str] | tuple[str, ...]) -> str:
    """Accord normalisé (`["ctrl", "b"]`) → syntaxe xdotool (`ctrl+b`)."""
    if not keys:
        raise ValueError("Accord vide")
    parts = []
    for key in keys:
        key = key.strip().lower()
        if key in KEYSYMS:
            parts.append(KEYSYMS[key])
        elif re.fullmatch(r"f([1-9]|1[0-2])", key):
            parts.append(key.upper())
        elif key.startswith("numpad") and key[6:].isdigit():
            parts.append(f"KP_{key[6:]}")
        elif re.fullmatch(r"[a-z0-9]", key):
            parts.append(key)
        else:
            raise ValueError(f"Touche non autorisée : {key!r}")
    return "+".join(parts)


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {k: v for k, v in {**os.environ, **(extra or {})}.items() if k in CHILD_ENV}


class DesktopSandbox:
    """Une application de bureau isolée, pilotée et observée comme le ferait l'apprenant."""

    def __init__(
        self,
        profile: AppProfile,
        *,
        width: int = 1280,
        height: int = 800,
        atspi_python: str = "/usr/bin/python3",
        launch_timeout: float = 60,
        snapshot_timeout: float = 30,
    ) -> None:
        if profile.generic is False or not profile.command:
            raise ValueError("Bac à sable de bureau réservé aux profils génériques avec commande")
        self.profile = profile
        self.width, self.height = width, height
        self.atspi_python = atspi_python
        self.launch_timeout = launch_timeout
        self.snapshot_timeout = snapshot_timeout
        self._workspace = tempfile.TemporaryDirectory(prefix=f"hcompany-{profile.id}-")
        self.root = Path(self._workspace.name)
        self.env: dict[str, str] = {}
        self._services: list[asyncio.subprocess.Process] = []
        self._app: asyncio.subprocess.Process | None = None
        self._document: Path | None = None
        self._document_dirty = False
        self._opened_sha: str | None = None
        self.metrics: list[dict[str, Any]] = []
        self.outcomes = profile.outcome_adapter(self) if profile.outcome_adapter else None

    async def __aenter__(self) -> DesktopSandbox:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _measure(self, operation: str, started: float, **extra: Any) -> float:
        duration = time.perf_counter() - started
        self.metrics.append({"operation": operation, "duration": duration, **extra})
        return duration

    async def _spawn(
        self, *argv: str, env: dict[str, str] | None = None
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            *argv,
            env=env or self.env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

    async def _run(self, *argv: str, timeout: float = 15, stdin: bytes | None = None) -> bytes:
        process = await asyncio.create_subprocess_exec(
            *argv,
            env=self.env,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout)
        except (TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError(
                f"{argv[0]} a échoué ({process.returncode}) : {stderr.decode()[:800]}"
            )
        return stdout

    async def start(self) -> None:
        missing = [
            tool for tool in ("Xvfb", "dbus-daemon", "xdotool", "import") if not shutil.which(tool)
        ]
        if missing:
            raise RuntimeError(f"Outils du bac à sable absents : {', '.join(missing)}")
        started = time.perf_counter()
        display = next(
            n
            for n in range(90, 400)
            if not Path(f"/tmp/.X{n}-lock").exists() and not Path(f"/tmp/.X11-unix/X{n}").exists()
        )
        base = scrubbed_env({"DISPLAY": f":{display}", "HOME": str(self.root / "home")})
        (self.root / "home").mkdir()
        self.env = base
        self._services.append(
            await self._spawn(
                "Xvfb",
                f":{display}",
                "-screen",
                "0",
                f"{self.width}x{self.height}x24",
                "-nolisten",
                "tcp",
                env=base,
            )
        )
        deadline = time.monotonic() + 10
        while not Path(f"/tmp/.X11-unix/X{display}").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("Xvfb n'a pas démarré")
            await asyncio.sleep(0.1)
        bus = await asyncio.create_subprocess_exec(
            "dbus-daemon",
            "--session",
            "--nofork",
            "--print-address=1",
            env=base,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        self._services.append(bus)
        assert bus.stdout is not None
        address = (await asyncio.wait_for(bus.stdout.readline(), 10)).decode().strip()
        if not address:
            raise RuntimeError("Bus D-Bus de session indisponible")
        self.env = scrubbed_env({**base, "DBUS_SESSION_BUS_ADDRESS": address, **self.profile.env})
        launcher = next(
            (
                p
                for p in (
                    "/usr/libexec/at-spi-bus-launcher",
                    "/usr/lib/at-spi2-core/at-spi-bus-launcher",
                )
                if Path(p).exists()
            ),
            None,
        )
        if launcher:
            self._services.append(await self._spawn(launcher, "--launch-immediately"))
        else:
            LOGGER.warning("at-spi-bus-launcher absent : capteur d'accessibilité indisponible")
        if shutil.which("openbox"):
            self._services.append(await self._spawn("openbox"))
        await asyncio.sleep(0.5)
        self._measure("sandbox_start", started, display=display)

    async def close(self) -> None:
        await self._stop_app()
        for process in reversed(self._services):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), 5)
        self._services.clear()
        self._workspace.cleanup()

    async def version(self) -> str:
        if not self.profile.version_command:
            return "unknown"
        output = await self._run(*self.profile.version_command, timeout=30)
        match = re.search(self.profile.version_pattern, output.decode(errors="replace"))
        if not match:
            raise RuntimeError("Version de l'application introuvable")
        return match[1]

    async def prepare_fixture(self, source: Path | None) -> Path:
        """Document initial dans le format natif de l'application (copie, jamais l'original)."""
        suffix = self.profile.document_suffix or (source.suffix if source else "")
        target_dir = self.root / "fixture"
        target_dir.mkdir(exist_ok=True)
        if source is None:
            if not self.profile.convert_command:
                raise ValueError("Fixture requise pour cette application")
            source = target_dir / "empty.csv"
            source.write_text("")
        source = Path(source).resolve()
        if not source.is_file():
            raise ValueError(f"Fixture introuvable : {source}")
        if source.suffix == suffix or not self.profile.convert_command:
            target = target_dir / f"initial{source.suffix}"
            shutil.copyfile(source, target)
            return target
        if source.suffix not in self.profile.convertible_suffixes:
            raise ValueError(f"Fixture {source.suffix} non convertible vers {suffix}")
        started = time.perf_counter()
        values = {
            "src": str(source),
            "outdir": str(target_dir),
            "profile": str(self.root / "convert"),
        }
        await self._run(
            *(part.format(**values) for part in self.profile.convert_command), timeout=90
        )
        converted = target_dir / f"{source.stem}{suffix}"
        if not converted.exists():
            raise RuntimeError("Conversion de la fixture impossible")
        target = target_dir / f"initial{suffix}"
        converted.replace(target)
        self._measure("fixture_convert", started)
        return target

    async def _stop_app(self) -> None:
        if self._app is None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self._app.pid, signal.SIGKILL)
        await self._app.wait()
        self._app = None
        self._opened_sha = None
        await asyncio.sleep(0.5)

    async def open(self, checkpoint: Path, *, sha256: str | None = None) -> None:
        """Ouvre `checkpoint` (copie de travail) sauf s'il est déjà le document courant."""
        if self._app is not None and sha256 is not None and sha256 == self._opened_sha:
            return
        await self._stop_app()
        started = time.perf_counter()
        document = self.root / "work" / f"document{Path(checkpoint).suffix}"
        document.parent.mkdir(exist_ok=True)
        shutil.copyfile(checkpoint, document)
        self._document = document
        values = {"file": str(document), "profile": str(self.root / "profile")}
        argv = [part.format(**values) for part in self.profile.command]
        self._app = await self._spawn(*argv)
        deadline = time.monotonic() + self.launch_timeout
        windows: list[str] = []
        while time.monotonic() < deadline:
            await asyncio.sleep(1)
            if self._app.returncode is not None:
                raise RuntimeError(f"{self.profile.name} s'est arrêté au lancement")
            with contextlib.suppress(RuntimeError, TimeoutError):
                found = await self._run(
                    "xdotool",
                    "search",
                    "--onlyvisible",
                    "--name",
                    re.escape(document.stem),
                    timeout=5,
                )
                windows = found.decode().split()
            if windows:
                break
        if not windows:
            raise TimeoutError(f"Fenêtre {self.profile.name} absente après {self.launch_timeout} s")
        window = windows[0]
        for command in (
            ("windowmove", window, "0", "0"),
            ("windowsize", window, str(self.width), str(self.height)),
            ("windowactivate", "--sync", window),
        ):
            with contextlib.suppress(RuntimeError, TimeoutError):
                await self._run("xdotool", *command, timeout=5)
        a11y_deadline = time.monotonic() + 30
        while time.monotonic() < a11y_deadline:
            snapshot = await self.snapshot()
            if snapshot.get("windows"):
                break
            await asyncio.sleep(1)
        else:
            LOGGER.warning("Arbre d'accessibilité vide : vérification visuelle seulement")
        await asyncio.sleep(1)
        self._opened_sha = sha256
        self._document_dirty = False
        self._measure("app_open", started)

    async def save(self, checkpoint_out: Path, *, timeout: float = 20) -> Path:
        """Enregistre le document courant par le raccourci de l'application et le copie."""
        if self._document is None:
            raise RuntimeError("Aucun document ouvert")
        started = time.perf_counter()
        data = await self.document_snapshot(timeout=timeout)
        Path(checkpoint_out).write_bytes(data)
        self._measure("save", started)
        return Path(checkpoint_out)

    async def document_snapshot(self, *, timeout: float = 20) -> bytes:
        if self._document is None:
            raise RuntimeError("Aucun document ouvert")
        if not self._document_dirty:
            return self._document.read_bytes()
        await self.key(self.profile.save_keys)
        await asyncio.sleep(1)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            before = self._document.read_bytes()
            await asyncio.sleep(0.5)
            if before == self._document.read_bytes():
                self._document_dirty = False
                return before
        raise TimeoutError("Document instable pendant l'enregistrement")

    async def evaluate_app_check(self, check: dict[str, Any]) -> dict[str, Any]:
        if self.outcomes is None:
            return {"result": "unknown", "reason": "Adaptateur de document absent"}
        return await self.outcomes.evaluate(check)

    async def prepare_step(self, check: dict[str, Any]) -> str:
        if self.outcomes is None or check.get("name") not in self.outcomes.checks:
            return ""
        return await self.outcomes.prepare_step(check)

    async def focus_text(self, *, ancestor_role: str, ancestor_name: str) -> None:
        request = {
            "operation": "focus",
            "app": self.profile.accessible_name,
            "role": "text",
            "ancestor_role": ancestor_role,
            "ancestor_name": ancestor_name,
        }
        raw = await self._run(
            self.atspi_python,
            str(WORKER),
            timeout=self.snapshot_timeout,
            stdin=json.dumps(request).encode(),
        )
        result = json.loads(raw)
        jsonschema.validate(
            result,
            {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "error": {"enum": ["AMBIGUOUS_TARGET", "APP_NOT_FOUND"]},
                },
                "required": ["ok"],
                "additionalProperties": False,
            },
        )
        if not result["ok"]:
            raise RuntimeError("Cible de focus absente ou ambiguë")

    def mark_current(self, sha256: str) -> None:
        self._opened_sha = sha256

    async def screenshot(self) -> bytes:
        started = time.perf_counter()
        image = await self._run("import", "-window", "root", "png:-", timeout=15)
        self._measure("screenshot", started)
        if not image.startswith(b"\x89PNG"):
            raise RuntimeError("Capture invalide")
        return image

    async def snapshot(self, *, cells: list[str] | None = None) -> dict[str, Any]:
        """Instantané d'accessibilité normalisé (forme partagée AT-SPI/AX/UIA)."""
        if not self.profile.accessible_name:
            return {
                "complete": False,
                "nodes": [],
                "windows": [],
                "error": {"code": "APP_NOT_FOUND"},
            }
        started = time.perf_counter()
        request = {
            "operation": "snapshot",
            "app": self.profile.accessible_name,
            "cells": cells or [],
        }
        try:
            raw = await self._run(
                self.atspi_python,
                str(WORKER),
                timeout=self.snapshot_timeout,
                stdin=json.dumps(request).encode(),
            )
        except TimeoutError:
            self._measure("a11y_snapshot", started, error="TIMEOUT")
            return {"complete": False, "nodes": [], "windows": [], "error": {"code": "TIMEOUT"}}
        except RuntimeError as exc:
            self._measure("a11y_snapshot", started, error="WORKER")
            return {
                "complete": False,
                "nodes": [],
                "windows": [],
                "error": {"code": "PERMISSION_DENIED", "message": str(exc)[:300]},
            }
        try:
            result = json.loads(raw)
            jsonschema.Draft202012Validator(WORKER_SCHEMA).validate(result)
        except (ValueError, UnicodeDecodeError, jsonschema.ValidationError):
            self._measure("a11y_snapshot", started, error="INVALID_PACKET")
            return {
                "complete": False,
                "nodes": [],
                "windows": [],
                "error": {"code": "INVALID_PACKET", "message": "Paquet AT-SPI invalide"},
            }
        if (result.get("error") or {}).get("code") == "APP_NOT_FOUND":
            # Application désinscrite du bus (LibreOffice après certains assistants) :
            # le prochain open relance l'application pour retrouver l'arbre.
            self._opened_sha = None
        result["platform"] = "linux"
        result["api"] = "atspi"
        self._measure("a11y_snapshot", started, nodes=len(result.get("nodes", [])))
        return result

    async def click(self, x: int, y: int, button: str = "left") -> None:
        code = {"left": "1", "middle": "2", "right": "3"}[button]
        self._document_dirty = True
        await self._run("xdotool", "mousemove", "--sync", str(x), str(y), "click", code)

    async def type_text(self, text: str) -> None:
        self._document_dirty = True
        await self._run("xdotool", "type", "--delay", "40", "--", text, timeout=60)

    async def key(self, keys: list[str] | tuple[str, ...]) -> None:
        self._document_dirty = True
        await self._run("xdotool", "key", "--clearmodifiers", xdotool_chord(keys))

    async def execute(self, action: dict[str, Any], *, image_size: tuple[int, int]) -> None:
        """Action native normalisée (`input.action` : click 0-1000, type, key)."""
        if action["type"] == "click":
            width, height = image_size
            x = round(float(action["x"]) * width / 1000)
            y = round(float(action["y"]) * height / 1000)
            await self.click(
                min(max(x, 0), width - 1), min(max(y, 0), height - 1), action.get("button", "left")
            )
        elif action["type"] == "type":
            await self.type_text(action["text"])
        elif action["type"] == "key":
            await self.key(action["keys"])
        else:
            raise ValueError(f"Action non autorisée : {action['type']!r}")
