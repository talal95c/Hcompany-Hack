"""Linux X11 test helper ; consentement et verrou restent à la charge du caller."""

from __future__ import annotations

import asyncio
import math

from engine.services.holo import ALLOWED_KEYS
from engine.services.protocols import HoloAction


async def _command(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, _ = await process.communicate()
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        raise RuntimeError(f"{args[0]} exited with status {process.returncode}")
    return stdout


async def capture_x11(window_id: str | int | None = None) -> bytes:
    """Capture PNG du même window_id que l'exécuteur, ou de l'écran root."""
    return await _command("import", "-window", str(window_id) if window_id else "root", "png:-")


_KEYS = {
    "enter": "Return",
    "escape": "Escape",
    "backspace": "BackSpace",
    "delete": "Delete",
    "pageup": "Prior",
    "pagedown": "Next",
    "cmd": "super",
    "numpad0": "KP_0",
    "numpad1": "KP_1",
    "numpad3": "KP_3",
    "numpad7": "KP_7",
    "numpad_period": "KP_Decimal",
}


class XdotoolExecutor:
    def __init__(self, window_id: str | int | None = None) -> None:
        self.window_id = str(window_id) if window_id is not None else None

    async def __call__(self, action: HoloAction) -> str:
        if action.type == "done":
            raise ValueError("done n'est pas une action native")
        if action.type == "click":
            if (
                action.x is None
                or action.y is None
                or not all(math.isfinite(v) and 0 <= v <= 1000 for v in (action.x, action.y))
            ):
                raise ValueError("coordonnées invalides")
            if action.button not in ("left", "middle", "right"):
                raise ValueError("bouton invalide")
            if self.window_id is not None:
                raw = await _command("xdotool", "getwindowgeometry", "--shell", self.window_id)
                geometry = dict(
                    line.split("=", 1) for line in raw.decode().splitlines() if "=" in line
                )
                width, height = int(geometry["WIDTH"]), int(geometry["HEIGHT"])
                origin_x, origin_y = int(geometry["X"]), int(geometry["Y"])
            else:
                raw = await _command("xdotool", "getdisplaygeometry")
                width, height = map(int, raw.split())
                origin_x = origin_y = 0
            if width <= 0 or height <= 0:
                raise ValueError("géométrie vide")
            x = origin_x + round(action.x * (width - 1) / 1000)
            y = origin_y + round(action.y * (height - 1) / 1000)
            await _command("xdotool", "mousemove", "--sync", str(x), str(y))
            await _command(
                "xdotool", "click", {"left": "1", "middle": "2", "right": "3"}[action.button]
            )
        elif action.type == "type":
            if action.text is None:
                raise ValueError("texte absent")
            if self.window_id:
                await _command("xdotool", "windowactivate", "--sync", self.window_id)
            await _command("xdotool", "type", "--clearmodifiers", "--", action.text)
        elif action.type == "key":
            if not action.keys or any(k not in ALLOWED_KEYS for k in action.keys):
                raise ValueError("touches invalides")
            if self.window_id:
                await _command("xdotool", "windowactivate", "--sync", self.window_id)
            keys = "+".join(
                _KEYS.get(
                    k,
                    k.capitalize()
                    if k in {"tab", "up", "down", "left", "right", "home", "end"}
                    or k.startswith("f")
                    and k[1:].isdigit()
                    else k,
                )
                for k in action.keys
            )
            await _command("xdotool", "key", "--clearmodifiers", keys)
        else:
            raise ValueError("action inconnue")
        return "executed"
