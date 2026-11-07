import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires a native desktop and real local transport")


@pytest.fixture(scope="session")
def calc_environment(tmp_path_factory):
    if sys.platform != "linux":
        pytest.skip("Linux AT-SPI integration")
    if os.environ.get("HCOMPANY_LIVE") != "1":
        pytest.skip("opt-in native integration")
    required = (
        "Xvfb",
        "dbus-run-session",
        "soffice",
        "localc",
        "xdotool",
        "cargo",
        "bash",
        "python3",
        "timeout",
    )
    missing = [name for name in required if not shutil.which(name)]
    launchers = (
        Path("/usr/libexec/at-spi-bus-launcher"),
        Path("/usr/lib/at-spi2-core/at-spi-bus-launcher"),
    )
    launcher = next((path for path in launchers if path.is_file()), None)
    if missing or launcher is None:
        pytest.skip(
            f"native integration dependencies unavailable: {missing}, AT-SPI={bool(launcher)}"
        )
    work = tmp_path_factory.mktemp("native-calc")
    (work / "probe.csv").write_text("Dummy,Count\nAlpha,42\nBeta,7\n")
    env = dict(os.environ, AT_SPI_LAUNCHER=str(launcher))
    with (work / "session.log").open("w") as log:
        process = subprocess.Popen(
            [
                "dbus-run-session",
                "--",
                "bash",
                str(Path(__file__).with_name("calc_session.sh")),
                str(work),
            ],
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=log,
            env=env,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 45
            while not (work / "ready.json").exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail(f"private Calc session failed; diagnostics: {work}")
                time.sleep(0.1)
            env.pop("AT_SPI_BUS_ADDRESS", None)
            env.update(json.loads((work / "ready.json").read_text()))
            yield env
        finally:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
