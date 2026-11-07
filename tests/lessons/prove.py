"""Mesure du processus Blender, démarrage et arrêt inclus."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def prove(directory: Path, output: Path) -> dict:
    blender = shutil.which("blender")
    if blender is None:
        raise RuntimeError("Blender est introuvable")
    start = time.perf_counter()
    process = subprocess.run(
        [
            blender,
            "-b",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).with_name("blender_runner.py")),
            "--",
            str(directory),
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    wall_seconds = time.perf_counter() - start
    print(process.stdout, end="")
    if process.returncode:
        raise RuntimeError(process.stdout + process.stderr)
    result = json.loads(output.read_text())
    result["blender_wall_seconds"] = wall_seconds
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    manifest_path = directory / "proof" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["blender_wall_seconds"] = wall_seconds
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"{directory.name:10} TOTAL Blender (murale)   {wall_seconds:.6f} s")
    return result


if __name__ == "__main__":
    prove(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
