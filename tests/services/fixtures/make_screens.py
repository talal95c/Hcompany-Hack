"""Captures reproductibles de vraies fenêtres, sur un Xvfb privé (jamais :0).

Exécuter : python tests/services/fixtures/make_screens.py
Dépendances : Xvfb, xdotool, ImageMagick import, libreoffice-calc et /opt/blender/blender.
Le contexte calc_session est aussi utilisé par la recette live computer-use.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / ".runtime"


def command(*args: str, env: dict[str, str]) -> bytes:
    return subprocess.check_output(args, env=env, stderr=subprocess.DEVNULL, timeout=30)


@contextlib.contextmanager
def display_session(number: int) -> Iterator[dict[str, str]]:
    if number == 0 or Path(f"/tmp/.X11-unix/X{number}").exists():
        raise RuntimeError(f"display :{number} indisponible")
    RUNTIME.mkdir(exist_ok=True)
    runtime = RUNTIME / f"xdg-{number}"
    runtime.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    env = {
        **os.environ,
        "DISPLAY": f":{number}",
        "XDG_RUNTIME_DIR": str(runtime),
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "SAL_USE_VCLPLUGIN": "gen",
        "LANG": "en_US.UTF-8",
    }
    with (RUNTIME / f"xvfb-{number}.log").open("w") as log:
        process = subprocess.Popen(
            ["Xvfb", f":{number}", "-screen", "0", "1600x900x24", "-nolisten", "tcp"],
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 15
            while not Path(f"/tmp/.X11-unix/X{number}").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Xvfb non prêt")
                time.sleep(0.1)
            yield env
        finally:
            process.terminate()
            process.wait(timeout=10)


def select_a4(env: dict[str, str]) -> None:
    command("xdotool", "key", "--clearmodifiers", "ctrl+Home", env=env)
    command("xdotool", "key", "Down", "Down", "Down", env=env)
    time.sleep(0.5)


@contextlib.contextmanager
def calc_session(number: int = 77) -> Iterator[dict[str, str]]:
    with display_session(number) as env:
        profile = RUNTIME / f"calc-profile-{number}"
        user = profile / "user"
        user.mkdir(parents=True, exist_ok=True)
        (user / "registrymodifications.xcu").write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Misc">'
            '<prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value></prop>'
            "</item></oor:items>",
            encoding="utf-8",
        )
        document = RUNTIME / f"numbers-{number}.fods"
        document.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
            'office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.spreadsheet">'
            '<office:body><office:spreadsheet><table:table table:name="Sheet1">'
            + "".join(
                f'<table:table-row><table:table-cell office:value-type="float" '
                f'office:value="{value}"><text:p>{value}</text:p>'
                "</table:table-cell></table:table-row>"
                for value in (10, 20, 30)
            )
            + "</table:table></office:spreadsheet></office:body></office:document>",
            encoding="utf-8",
        )
        with (RUNTIME / f"calc-{number}.log").open("w") as log:
            process = subprocess.Popen(
                [
                    "soffice",
                    f"-env:UserInstallation={profile.as_uri()}",
                    "--norestore",
                    "--nofirststartwizard",
                    "--nologo",
                    str(document),
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 40
                while True:
                    try:
                        ids = command(
                            "xdotool",
                            "search",
                            "--onlyvisible",
                            "--class",
                            "libreoffice-calc",
                            env=env,
                        ).splitlines()
                        if ids:
                            break
                    except subprocess.CalledProcessError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("fenêtre Calc non prête")
                    time.sleep(0.3)
                window = ids[-1].decode()
                command("xdotool", "windowsize", window, "1600", "900", env=env)
                command("xdotool", "windowmove", window, "0", "0", env=env)
                command("xdotool", "windowfocus", "--sync", window, env=env)
                time.sleep(2)
                command("xdotool", "key", "Escape", env=env)
                select_a4(env)
                yield env
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def make_calc() -> None:
    with calc_session() as env:
        command("import", "-window", "root", str(HERE / "calc_no_formula.png"), env=env)
        command("xdotool", "type", "--clearmodifiers", "--", "=SUM(A1:A3)", env=env)
        command("xdotool", "key", "Return", env=env)
        select_a4(env)
        command("import", "-window", "root", str(HERE / "calc_sum_formula.png"), env=env)


def make_scene(kind: str, number: int) -> None:
    with display_session(number) as env:
        expression = (
            "import bpy; "
            "bpy.context.preferences.view.show_splash=False; "
            "bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False); "
            + (
                "bpy.ops.mesh.primitive_torus_add(major_radius=2, minor_radius=0.65); "
                if kind == "torus"
                else "bpy.ops.mesh.primitive_cube_add(); "
            )
            + "bpy.context.object.name='Subject'; "
            "bpy.context.scene.world.color=(0.15,0.15,0.15); "
        )
        with (RUNTIME / f"scene-{kind}.log").open("w") as log:
            process = subprocess.Popen(
                [
                    "/opt/blender/blender",
                    "--factory-startup",
                    "--gpu-backend",
                    "opengl",
                    "--window-geometry",
                    "0",
                    "0",
                    "1600",
                    "900",
                    "--python-expr",
                    expression,
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 40
                while True:
                    try:
                        ids = command(
                            "xdotool", "search", "--onlyvisible", "--class", "Blender", env=env
                        ).splitlines()
                        if ids:
                            break
                    except subprocess.CalledProcessError:
                        pass
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("fenêtre 3D non prête")
                    time.sleep(0.5)
                time.sleep(8)
                command("import", "-window", "root", str(HERE / f"blender_{kind}.png"), env=env)
            finally:
                process.terminate()
                process.wait(timeout=15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", choices=("all", "calc", "scene"), default="all")
    args = parser.parse_args()
    if args.app in ("all", "calc"):
        make_calc()
    if args.app in ("all", "scene"):
        make_scene("torus", 78)
        make_scene("cube", 79)


if __name__ == "__main__":
    main()
