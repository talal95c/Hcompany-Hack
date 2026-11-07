"""Exercise real native Rust backends, never cloud SDK stubs."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("HCOMPANY_LIVE") != "1", reason="opt-in native integration")
def test_native_capture_and_authenticated_websocket():
    result = subprocess.run(
        ["cargo", "test", "--locked", "live_", "--", "--ignored", "--nocapture"],
        cwd=ROOT / "desktop/src-tauri",
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stderr
    assert "2 passed" in result.stdout
