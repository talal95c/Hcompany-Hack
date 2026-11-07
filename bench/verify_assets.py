"""Captures fraîches, labels issus des capteurs et manifeste réutilisable."""

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from bench.a11y_session import A11ySession
from bench.common import ROOT

CALC_CONFIGS = [
    {},
    {"has_value": True},
    {"has_value": True, "bold": True},
    {"has_value": True, "italic": True},
    {"has_value": True, "underline": True},
    {"bold": True},
    {"has_value": True, "bold": True, "italic": True},
    {"has_value": True, "bold": True, "underline": True},
    {"has_value": True, "italic": True, "underline": True},
    {"has_value": True, "bold": True, "italic": True, "underline": True},
]
CALC_PAIRS = [
    ("cell_empty", "cell_has_value"),
    ("cell_has_value", "bold"),
    ("bold", "italic"),
    ("italic", "bold"),
    ("underline", "italic"),
    ("bold", "cell_has_value"),
    ("bold", "underline"),
    ("underline", "italic"),
    ("italic", "bold"),
    ("italic", "cell_empty"),
]
BLENDER_PAIRS = [
    ("has_cube", "has_torus"),
    ("empty_scene", "has_cube"),
    ("has_torus", "has_cube"),
    ("has_sphere", "has_torus"),
    ("editing", "has_torus"),
    ("editing", "has_cube"),
    ("modifier_panel", "editing"),
    ("two_meshes", "empty_scene"),
    ("has_cube", "has_sphere"),
    ("sidebar", "editing"),
]
ASSERTIONS = {
    "cell_empty": "La cellule A1 est-elle vide ?",
    "cell_has_value": "La cellule A1 contient-elle la valeur 424242 ?",
    "bold": "Le bouton Gras de la barre d'outils est-il activé ?",
    "italic": "Le bouton Italique de la barre d'outils est-il activé ?",
    "underline": "Le bouton Souligné de la barre d'outils est-il activé ?",
    "has_cube": "Un cube est-il présent dans la scène ?",
    "has_torus": "Un tore est-il présent dans la scène ?",
    "has_sphere": "Une sphère est-elle présente dans la scène ?",
    "empty_scene": "La scène est-elle vide de tout objet ?",
    "editing": "L'objet actif est-il en mode Édition ?",
    "modifier_panel": "L'onglet Modificateurs est-il ouvert dans l'éditeur de propriétés ?",
    "two_meshes": "La scène contient-elle exactement deux objets maillages ?",
    "sidebar": "Le panneau latéral Item/Transform est-il ouvert à droite de la vue 3D ?",
}


def optimize(path: Path) -> tuple[int, int]:
    with Image.open(path) as source:
        image = source.convert("RGB")
    if max(high - low for low, high in image.getextrema()) < 20:
        raise ValueError("Capture vide")
    image.thumbnail((1280, 900))
    image.save(path, optimize=True)
    return image.size


def scene_record(app: str, index: int, path: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    pairs = CALC_PAIRS if app == "calc" else BLENDER_PAIRS
    questions = [
        {
            "id": f"{app}-{index:02d}-{fact}",
            "assertion": ASSERTIONS[fact],
            "fact": fact,
            "expected": "yes" if evidence["facts"][fact] else "no",
        }
        for fact in pairs[index]
    ]
    if {q["expected"] for q in questions} != {"yes", "no"}:
        raise ValueError("État capteur inattendu : labels déséquilibrés")
    if app == "calc":
        for question in questions:
            question["region"] = {"x": 0, "y": 0, "w": 1000, "h": 450}
    size = optimize(path)
    return {
        "id": f"{app}-{index:02d}",
        "app": app,
        "sensor": "accessibility" if app == "calc" else "bpy",
        "image": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "image_size": list(size),
        "captured_at": datetime.now(UTC).isoformat(),
        "evidence": evidence,
        "questions": questions,
    }


async def generate_calc(out: Path) -> list[dict[str, Any]]:
    records = []
    for index, config in enumerate(CALC_CONFIGS):
        async with A11ySession() as session:
            startup = await session.launch_calc()
            await session.request("configure_cell", **config)
            before = (await session.request("verify_cell_state"))["result"]
            for key in ("bold", "italic", "underline"):
                if before["facts"][key] != config.get(key, False):
                    raise ValueError("Format Calc non confirmé par AT-SPI")
            if before["facts"]["cell_has_value"] != config.get("has_value", False):
                raise ValueError("Valeur Calc non confirmée par AT-SPI")
            path = out / f"calc-{index:02d}.png"
            await session.request("capture", path=str(path.resolve()))
            after = (await session.request("verify_cell_state"))["result"]
            if before != after:
                raise ValueError("État Calc modifié pendant la capture")
            records.append(scene_record("calc", index, path, {**before, "startup": startup}))
    return records


async def command(*args: str, **kwargs: Any) -> None:
    process = await asyncio.create_subprocess_exec(*args, **kwargs)
    try:
        if await asyncio.wait_for(process.wait(), 15):
            raise RuntimeError("Commande de capture échouée")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def generate_blender(out: Path, blender: str) -> list[dict[str, Any]]:
    records = []
    with tempfile.TemporaryDirectory(prefix="verify-blender-") as temporary:
        runtime = Path(temporary)
        os.chmod(runtime, 0o700)
        with tempfile.TemporaryFile() as display_file:
            xvfb = await asyncio.create_subprocess_exec(
                "Xvfb",
                "-displayfd",
                str(display_file.fileno()),
                "-screen",
                "0",
                "1600x1000x24",
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
                    await asyncio.sleep(0.05)
                else:
                    raise TimeoutError("Xvfb indisponible")
                env = {
                    **os.environ,
                    "DISPLAY": ":" + display,
                    "XDG_RUNTIME_DIR": temporary,
                    "LIBGL_ALWAYS_SOFTWARE": "1",
                    "MESA_GL_VERSION_OVERRIDE": "4.5",
                }
                with (out / "blender-generation.log").open("wb") as log:
                    process = await asyncio.create_subprocess_exec(
                        blender,
                        "--factory-startup",
                        "--gpu-backend",
                        "opengl",
                        "-p",
                        "0",
                        "0",
                        "1600",
                        "1000",
                        "--python-exit-code",
                        "1",
                        "--python",
                        str(ROOT / "bench/blender/render_verify.py"),
                        "--",
                        "--out",
                        str(runtime),
                        env=env,
                        stdout=log,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    for index in range(len(BLENDER_PAIRS)):
                        evidence_path = runtime / f"blender-{index:02d}.evidence.json"
                        for _ in range(600):
                            if evidence_path.exists():
                                break
                            if process.returncode is not None:
                                raise RuntimeError("Blender arrêté avant capture")
                            await asyncio.sleep(0.1)
                        else:
                            raise TimeoutError("Scène Blender indisponible")
                        evidence = json.loads(evidence_path.read_text())
                        if evidence["window_size"] != [1600, 1000]:
                            raise ValueError("Fenêtre Blender différente du display")
                        path = out / f"blender-{index:02d}.png"
                        await command("import", "-window", "root", str(path), env=env)
                        records.append(scene_record("blender", index, path, evidence))
                        (runtime / f"blender-{index:02d}.ack").write_text("capturé")
                    await asyncio.wait_for(process.wait(), 15)
                    if process.returncode:
                        raise RuntimeError("Blender arrêté avec erreur")
            finally:
                if process is not None and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                xvfb.terminate()
                await xvfb.wait()
    return records


def validate_manifest(manifest: dict[str, Any], root: Path) -> None:
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("version")) is not int
        or manifest.get("version") != 1
        or not isinstance(manifest.get("scenes"), list)
    ):
        raise ValueError("Manifeste invalide")
    counts = {"calc": 0, "blender": 0}
    identifiers = set()
    questions_count = 0
    for scene in manifest["scenes"]:
        try:
            app = scene["app"]
            if app not in counts or scene["sensor"] != (
                "accessibility" if app == "calc" else "bpy"
            ):
                raise ValueError
            counts[app] += 1
            if scene["id"] in identifiers:
                raise ValueError
            identifiers.add(scene["id"])
            path = (root / scene["image"]).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError
            if hashlib.sha256(path.read_bytes()).hexdigest() != scene["sha256"]:
                raise ValueError
            with Image.open(path) as image:
                if list(image.size) != scene["image_size"] or image.format != "PNG":
                    raise ValueError
            questions = scene["questions"]
            if len(questions) < 2 or {q["expected"] for q in questions} != {"yes", "no"}:
                raise ValueError
            for question in questions:
                if question["id"] in identifiers or not 1 <= len(question["assertion"]) <= 300:
                    raise ValueError
                identifiers.add(question["id"])
                fact = scene["evidence"]["facts"][question["fact"]]
                if type(fact) is not bool or question["expected"] != ("yes" if fact else "no"):
                    raise ValueError
                region = question.get("region")
                if region is not None:
                    if set(region) != {"x", "y", "w", "h"} or any(
                        type(v) not in (int, float) or not 0 <= v <= 1000 for v in region.values()
                    ):
                        raise ValueError
                    if (
                        region["w"] <= 0
                        or region["h"] <= 0
                        or (region["x"] + region["w"] > 1000 or region["y"] + region["h"] > 1000)
                    ):
                        raise ValueError
            questions_count += len(questions)
        except (KeyError, TypeError, OSError) as error:
            raise ValueError("Scène du manifeste invalide") from error
    if min(counts.values()) < 8 or questions_count < 40:
        raise ValueError("Dataset incomplet : 8 scènes par application et 40 questions minimum")


async def ensure_assets(root: Path, blender: str, reuse: bool = False) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    if reuse:
        manifest = json.loads(path.read_text())
    else:
        manifest = {
            "version": 1,
            "scenes": [*await generate_calc(root), *await generate_blender(root, blender)],
        }
        validate_manifest(manifest, root)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    validate_manifest(manifest, root)
    return manifest
