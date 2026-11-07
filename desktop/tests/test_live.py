"""Exercise real native Rust backends, never cloud SDK stubs."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("HCOMPANY_LIVE") != "1", reason="opt-in native integration")
@pytest.mark.parametrize(
    "native_test",
    [
        "native::live_tests::live_native_capture",
        "transport::tests::live_loopback_auth_and_protocol",
    ],
)
def test_native_capture_and_authenticated_websocket(native_test, request):
    environment = request.getfixturevalue("calc_environment") if sys.platform == "linux" else None
    result = subprocess.run(
        ["cargo", "test", "--locked", native_test, "--", "--exact", "--ignored", "--nocapture"],
        cwd=ROOT / "desktop/src-tauri",
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
        check=False,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stderr
    assert "1 passed" in result.stdout
