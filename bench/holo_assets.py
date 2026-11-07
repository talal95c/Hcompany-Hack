"""Generate screenshot evidence and geometry without production-module imports."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from bench.common import ROOT


async def render(scale: int, out: Path, blender: str = "/opt/blender/blender") -> None:
    out.mkdir(parents=True, exist_ok=True)
    width, height = (1920, 1080) if scale == 1 else (3840, 2160)
    geometry = out / f"scale-{scale}.json"
    screenshot = out / f"scale-{scale}.png"
    geometry.unlink(missing_ok=True)
    runtime = Path.home() / ".cache" / "blender-runtime"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryFile() as display_file:
        xvfb = await asyncio.create_subprocess_exec(
            "Xvfb",
            "-displayfd",
            str(display_file.fileno()),
            "-screen",
            "0",
            f"{width}x{height}x24",
            "-nolisten",
            "tcp",
            pass_fds=(display_file.fileno(),),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        process = None
        try:
            for _ in range(100):
                display_file.seek(0)
                display = display_file.read().decode().strip()
                if display:
                    break
                await asyncio.sleep(0.1)
            else:
                raise TimeoutError("Xvfb did not start")
            env = {
                **os.environ,
                "DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "LIBGL_ALWAYS_SOFTWARE": "1",
                "MESA_GL_VERSION_OVERRIDE": "4.5",
            }
            with (out / f"scale-{scale}.log").open("wb") as log:
                process = await asyncio.create_subprocess_exec(
                    blender,
                    "--factory-startup",
                    "--gpu-backend",
                    "opengl",
                    "-p",
                    "0",
                    "0",
                    str(width),
                    str(height),
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(ROOT / "bench/blender/render_holo.py"),
                    "--",
                    "--scale",
                    str(scale),
                    "--out",
                    str(geometry.resolve()),
                    env=env,
                    stdout=log,
                    stderr=asyncio.subprocess.STDOUT,
                )
                for _ in range(300):
                    if geometry.exists():
                        break
                    if process.returncode is not None:
                        raise RuntimeError("Blender exited before geometry export")
                    await asyncio.sleep(0.1)
                else:
                    raise TimeoutError("Blender geometry not ready")
                capture = await asyncio.create_subprocess_exec(
                    "import",
                    "-window",
                    "root",
                    str(screenshot.resolve()),
                    env=env,
                )
                if await capture.wait():
                    raise RuntimeError("External X screenshot failed")
                image = Image.open(screenshot).convert("RGB")
                if max(high - low for low, high in image.getextrema()) < 20:
                    raise RuntimeError("Blank screenshot")
                image.save(screenshot, optimize=True)
        finally:
            if process and process.returncode is None:
                process.terminate()
                await process.wait()
            xvfb.terminate()
            await xvfb.wait()


def top_left(rect: dict[str, Any], height: int) -> list[int]:
    return [
        rect["x"],
        height - rect["y"] - rect["height"],
        rect["x"] + rect["width"],
        height - rect["y"],
    ]


def crop_box(area: list[int], size: tuple[int, int], margin: int = 24) -> list[int]:
    return [
        max(0, area[0] - margin),
        max(0, area[1] - margin),
        min(size[0], area[2] + margin),
        min(size[1], area[3] + margin),
    ]


def map_point(point: tuple[float, float], box: list[int]) -> tuple[float, float]:
    return (
        box[0] + point[0] / 1000 * (box[2] - box[0]),
        box[1] + point[1] / 1000 * (box[3] - box[1]),
    )


def hit(point: tuple[float, float] | None, box: list[int]) -> bool:
    return point is not None and box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


TARGETS = [
    ("VIEW_3D", "HEADER", "En-tête de la vue 3D / 3D viewport header"),
    (
        "VIEW_3D",
        "TOOL_HEADER",
        "Réglages de l'outil actif dans la vue 3D / viewport tool settings header",
    ),
    ("VIEW_3D", "TOOLS", "Barre d'outils à gauche de la vue 3D / left viewport toolbar"),
    ("VIEW_3D", "UI", "Panneau latéral N de la vue 3D / viewport N sidebar"),
    ("VIEW_3D", "WINDOW", "Zone centrale de la vue 3D / main 3D viewport"),
    ("OUTLINER", "WINDOW", "Liste des objets de l'Outliner / Outliner object list"),
    ("OUTLINER", "HEADER", "En-tête de l'Outliner / Outliner header"),
    ("PROPERTIES", "NAVIGATION_BAR", "Colonne des onglets des propriétés / Properties tabs"),
    ("PROPERTIES", "WINDOW", "Panneau principal des propriétés / Properties main panel"),
    ("PROPERTIES", "HEADER", "En-tête des propriétés / Properties header"),
    ("DOPESHEET_EDITOR", "WINDOW", "Zone de la timeline / Timeline area"),
    ("DOPESHEET_EDITOR", "HEADER", "En-tête de la timeline / Timeline header"),
]


def probes(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    window = geometry["windows"][0]
    result = []
    for area_type, region_type, description in TARGETS:
        candidates = [
            (area, region)
            for area in window["areas"]
            if area["type"] == area_type
            for region in area["regions"]
            if region["type"] == region_type and region["width"] > 1 and region["height"] > 1
        ]
        if not candidates:
            raise ValueError(f"Missing region: {area_type}/{region_type}")
        area, region = candidates[0]
        result.append(
            {
                "id": f"{area_type}/{region_type}",
                "description": description,
                "box": top_left(region, window["height"]),
                "parent": top_left(area, window["height"]),
            }
        )
    return result


async def ensure_assets(out: Path, blender: str) -> None:
    for scale in (1, 2):
        if not (out / f"scale-{scale}.png").exists():
            await render(scale, out, blender)
        geometry = json.loads((out / f"scale-{scale}.json").read_text())
        probes(geometry)
