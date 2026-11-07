"""Opt-in Rust-native fallback, not a Tauri/engine WebSocket acceptance test."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live
def test_private_calc_accessibility(calc_environment):
    result = subprocess.run(
        [
            "cargo",
            "test",
            "--locked",
            "a11y::tests::live_accessibility",
            "--",
            "--exact",
            "--ignored",
            "--nocapture",
        ],
        cwd=ROOT / "desktop/src-tauri",
        env=calc_environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stderr
    assert "1 passed" in result.stdout
    assert "app.focus discovery + window PNG dimensions" in result.stdout
