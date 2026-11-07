"""Exercise the exact `python -m engine` process lifecycle in isolation."""

import os
import runpy
import sys
from pathlib import Path

probe = Path(__file__).resolve().parents[2] / "ws_probe.py"
sys.argv = [str(probe), "--port", os.environ["ENGINE_PORT"], "--output",
            os.environ["HCOMPANY_PROBE_OUTPUT"], "--sidecar"]
runpy.run_path(str(probe), run_name="__main__")
