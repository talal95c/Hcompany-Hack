"""Statistiques et rapports reproductibles."""

import json
import math
import platform
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], percent: float) -> float | None:
    """Nearest-rank: sorted[ceil(n*p/100)-1]; empty input gives None."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * percent / 100) - 1)]


def statistics(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "max_ms": max(values) if values else None,
    }


class Timer:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000


def metadata() -> dict[str, Any]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            cpu,
        )
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "hostname": socket.gethostname(),
        "cpu": cpu,
        "python": platform.python_version(),
    }


def write_report(suite: str, report: dict[str, Any], out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    report = {"suite": suite, "metadata": metadata(), **report}
    if "blender_version" in report:
        report["metadata"]["blender_version"] = report["blender_version"]
    (out / f"{suite}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    lines = [
        f"# Benchmark {suite}",
        "",
        f"Mesuré le {report['metadata']['timestamp_utc']}",
        "",
        "| Mesure | Valeur |",
        "|---|---|",
    ]
    for key, value in report.get("summary", {}).items():
        lines.append(f"| {key} | {json.dumps(value, ensure_ascii=False)} |")
    lines += [
        "",
        *report.get("notes", []),
        "",
        "## Métadonnées",
        "",
        "```json",
        json.dumps(report["metadata"], indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    markdown = "\n".join(lines)
    (out / f"{suite}.md").write_text(markdown)
    return markdown
