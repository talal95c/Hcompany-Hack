"""Sonde AT-SPI isolée, exécutée avec le Python système (3.10 compatible)."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter, deque
from pathlib import Path

TEST_VALUE = "424242"


class Probe:
    def __init__(self):
        self.processes = []
        self.profile = tempfile.TemporaryDirectory(prefix="calc-profile-")
        self.calc = None
        self.app = None

    def spawn(self, *args, **kwargs):
        process = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs
        )
        self.processes.append(process)
        return process

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(self.processes):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self.profile.cleanup()

    def start(self, plugin="gtk3", timeout=60):
        with tempfile.TemporaryFile() as display_file:
            display = self.spawn(
                "Xvfb",
                "-displayfd",
                str(display_file.fileno()),
                "-screen",
                "0",
                "1600x1000x24",
                "-nolisten",
                "tcp",
                pass_fds=(display_file.fileno(),),
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                display_file.seek(0)
                number = display_file.read().decode().strip()
                if number:
                    break
                if display.poll() is not None:
                    raise RuntimeError("xvfb_exit")
                time.sleep(0.05)
            else:
                raise TimeoutError("xvfb_timeout")
        os.environ.update(
            DISPLAY=":" + number,
            GTK_MODULES="gail:atk-bridge",
            SAL_USE_VCLPLUGIN=plugin,
            NO_AT_BRIDGE="0",
            SAL_ACCESSIBILITY_ENABLED="1",
            GTK_USE_PORTAL="0",
            GNOME_ACCESSIBILITY="1",
        )
        subprocess.run(
            [
                "dbus-update-activation-environment",
                "DISPLAY",
                "XDG_RUNTIME_DIR",
                "GTK_MODULES",
                "NO_AT_BRIDGE",
            ],
            check=True,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.spawn("/usr/libexec/at-spi-bus-launcher", "--launch-immediately", "--a11y=1")
        self.spawn("/usr/libexec/at-spi2-registryd")
        time.sleep(1)
        started = time.perf_counter()
        self.calc = self.spawn(
            "localc",
            "-env:UserInstallation=" + Path(self.profile.name).as_uri(),
            "--norestore",
            "--nologo",
        )
        deadline = time.monotonic() + timeout
        bus_ms = None
        while time.monotonic() < deadline:
            self.alive()
            ready = self.query(
                {"op": "ready"}, timeout=min(5, max(0.1, deadline - time.monotonic()))
            )
            if ready["result"]["on_bus"] and bus_ms is None:
                bus_ms = (time.perf_counter() - started) * 1000
            if ready["result"]["frame_ready"]:
                return {
                    "time_to_bus_ms": bus_ms,
                    "time_to_window_ms": (time.perf_counter() - started) * 1000,
                    "app_name": "soffice",
                    "display": os.environ["DISPLAY"],
                    "plugin": plugin,
                    "system_python": sys.version.split()[0],
                    "pid": self.calc.pid,
                }
            time.sleep(0.5)
        raise TimeoutError("calc_window_timeout" if bus_ms else "calc_bus_timeout")

    def query(self, request, timeout=15):
        process = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--query"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if process.returncode:
            raise RuntimeError("probe_exit:" + str(process.returncode))
        return json.loads(process.stdout)

    def connect(self):
        import pyatspi

        self.atspi = pyatspi
        pyatspi.setTimeout(1500, 3000)
        desktop = pyatspi.Registry.getDesktop(0)
        self.app = next((app for app in desktop if app and app.name == "soffice"), None)

    def ready(self):
        return {
            "on_bus": self.app is not None,
            "frame_ready": self.app is not None and self.app.childCount > 0,
        }

    def alive(self):
        if self.calc is not None and self.calc.poll() is not None:
            raise RuntimeError("calc_exit:" + str(self.calc.returncode))

    def walk(self, max_nodes=1200, max_depth=12, skip_tables=False):
        self.walk_truncated = False
        stack = deque([(self.app, 0)])
        visited = 0
        while stack and visited < max_nodes:
            node, depth = stack.popleft()
            if node is None:
                continue
            visited += 1
            yield node, depth
            if depth >= max_depth or (
                skip_tables
                and node.getRoleName()
                in (
                    "table",
                    "tree table",
                    "spreadsheet",
                    "document spreadsheet",
                    "menu bar",
                    "menu",
                )
            ):
                if depth >= max_depth and node.childCount:
                    self.walk_truncated = True
                continue
            count = min(node.childCount, max_nodes - visited - len(stack))
            if count < node.childCount:
                self.walk_truncated = True
            for index in range(count):
                stack.append((node.getChildAtIndex(index), depth + 1))

    def snapshot(self, max_nodes=1200, max_depth=12):
        roles = Counter()
        size = 0
        depth_seen = 0
        depth_limited = False
        for node, depth in self.walk(max_nodes, max_depth):
            roles[node.getRoleName()] += 1
            size += 1
            depth_seen = max(depth_seen, depth)
            if depth == max_depth and node.childCount:
                depth_limited = True
        return {
            "node_count": size,
            "max_depth": depth_seen,
            "roles": dict(roles),
            "truncated": self.walk_truncated or depth_limited,
        }

    def describe(self, node):
        rect = node.queryComponent().getExtents(self.atspi.DESKTOP_COORDS)
        states = [state.value_nick for state in node.getState().getStates()]
        return {
            "role": node.getRoleName(),
            "name": node.name,
            "bounds": [rect.x, rect.y, rect.width, rect.height],
            "states": states,
        }

    def find(self, name):
        for node, _ in self.walk(skip_tables=True):
            if node.name == name and node.getRoleName() in ("push button", "toggle button"):
                description = self.describe(node)
                if description["bounds"][2] > 0 and description["bounds"][3] > 0:
                    return description
        return None

    def discover(self):
        return [
            self.describe(node)
            for node, _ in self.walk(skip_tables=True)
            if node.getRoleName() in ("push button", "toggle button") and node.name
        ]

    def write_cell(self):
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "Escape", "ctrl+Home"],
            check=True,
            timeout=5,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", TEST_VALUE],
            check=True,
            timeout=5,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["xdotool", "key", "Return", "ctrl+Home"],
            check=True,
            timeout=5,
            stdout=subprocess.DEVNULL,
        )
        return {"typed": True}

    def read_cell(self):
        for node, _ in self.walk(max_nodes=2000):
            if node.getRoleName() == "table":
                cell = node.queryTable().getAccessibleAt(0, 0)
                text = cell.queryText().getText(0, -1)
                return {"correct": text == TEST_VALUE, "cell": "A1", "role": cell.getRoleName()}
        raise RuntimeError("cell_unavailable")

    def configure_cell(self, has_value=False, bold=False, italic=False, underline=False):
        for node, _ in self.walk(max_nodes=2000):
            if node.getRoleName() == "table":
                cell = node.queryTable().getAccessibleAt(0, 0)
                rect = cell.queryComponent().getExtents(self.atspi.DESKTOP_COORDS)
                if rect.width <= 0 or rect.height <= 0:
                    raise RuntimeError("cell_not_visible")
                subprocess.run(
                    [
                        "xdotool",
                        "mousemove",
                        "--sync",
                        str(rect.x + rect.width // 2),
                        str(rect.y + rect.height // 2),
                        "click",
                        "1",
                    ],
                    check=True,
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                )
                break
        else:
            raise RuntimeError("cell_unavailable")
        if has_value:
            self.write_cell()
        time.sleep(0.2)
        for enabled, name in ((bold, "Bold"), (italic, "Italic"), (underline, "Underline")):
            if enabled:
                for node, _ in self.walk(skip_tables=True):
                    if node.name == name and node.getRoleName() in ("push button", "toggle button"):
                        if not node.queryAction().doAction(0):
                            raise RuntimeError("format_action_failed")
                        break
                else:
                    raise RuntimeError("format_button_unavailable")
        time.sleep(0.3)
        return {"configured": True}

    def verify_cell_state(self):
        facts = {}
        for node, _ in self.walk(max_nodes=2000):
            if node.getRoleName() == "table":
                cell = node.queryTable().getAccessibleAt(0, 0)
                text = cell.queryText().getText(0, -1)
                if text not in ("", TEST_VALUE):
                    raise RuntimeError("unexpected_cell_value:length=" + str(len(text)))
                facts.update(cell_has_value=text == TEST_VALUE, cell_empty=text == "")
                break
        if not facts:
            raise RuntimeError("cell_unavailable")
        buttons = {}
        for key, name in (("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline")):
            button = self.find(name)
            if button is None:
                raise RuntimeError("format_button_unavailable")
            buttons[key] = button
            facts[key] = "checked" in button["states"] or "pressed" in button["states"]
        return {"facts": facts, "buttons": buttons, "cell": "A1"}

    def capture(self, path):
        identifiers = subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--name", "LibreOffice Calc"],
            text=True,
            timeout=5,
        ).splitlines()
        if len(identifiers) != 1:
            raise RuntimeError("ambiguous_capture_window")
        subprocess.run(["import", "-window", identifiers[0], path], check=True, timeout=10)
        return {"window_id": identifiers[0]}

    def dispatch(self, request):
        op = request["op"]
        if op != "start":
            self.alive()
            response = self.query(request)
            self.alive()
            return response
        return self.execute(request)

    def execute(self, request):
        op = request["op"]
        if op != "start":
            self.connect()
            if self.app is None and op != "ready":
                raise RuntimeError("calc_not_on_bus")
        method = (
            getattr(self, op)
            if op
            in {
                "start",
                "snapshot",
                "find",
                "discover",
                "write_cell",
                "read_cell",
                "ready",
                "configure_cell",
                "verify_cell_state",
                "capture",
            }
            else None
        )
        if method is None:
            raise ValueError("invalid_operation")
        started = time.perf_counter()
        result = method(**request.get("arguments", {}))
        self.alive()
        return {"result": result, "latency_ms": (time.perf_counter() - started) * 1000}


def main():
    probe = Probe()
    if sys.argv[1:] == ["--query"]:
        try:
            response = probe.execute(json.load(sys.stdin))
        except Exception as error:
            response = {"error": type(error).__name__ + ":" + str(error)}
        print(json.dumps(response), flush=True)
        probe.close()
        return

    def terminate(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    try:
        for line in sys.stdin:
            try:
                response = probe.dispatch(json.loads(line))
            except Exception as error:
                response = {"error": type(error).__name__ + ":" + str(error)}
            print(json.dumps(response), flush=True)
    finally:
        probe.close()


if __name__ == "__main__":
    main()
