"""Lance le pilote système dans un bus et un affichage isolés."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prove(directory: Path, output: Path, *, native_only: bool = False) -> dict:
    from jsonschema import Draft202012Validator

    lesson = json.loads((directory / "lesson.json").read_text())
    companion = json.loads((directory / "steps.json").read_text())
    for value, schema in [
        (lesson, ROOT / "contracts/lesson.schema.json"),
        (companion, ROOT / "lessons/generic-steps.schema.json"),
    ]:
        Draft202012Validator(json.loads(schema.read_text())).validate(value)
    env = {**os.environ, "LESSON_API_PYTHON": sys.executable}
    args = [
        "dbus-run-session",
        "--",
        "bash",
        str(HERE / "a11y_session.sh"),
        str(directory.resolve()),
        str(output.resolve()),
    ]
    if native_only:
        args.append("--native-only")
    process = subprocess.Popen(args, env=env, start_new_session=True)
    try:
        code = process.wait(timeout=420)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        raise
    if code:
        raise RuntimeError(f"Preuve interrompue : code {code}")
    return json.loads(output.read_text())


if __name__ == "__main__":
    prove(Path(sys.argv[1]), Path(sys.argv[2]), native_only="--native-only" in sys.argv)
