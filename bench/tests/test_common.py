import json
from pathlib import Path

import pytest

from bench.common import Timer, percentile, write_report


def test_percentile() -> None:
    assert percentile([], 50) is None
    assert percentile([4, 1, 3, 2], 50) == 2
    assert percentile([4, 1, 3, 2], 95) == 4
    assert percentile([1], 0) == 1
    with pytest.raises(ValueError):
        percentile([1], 101)
    assert Timer().elapsed_ms >= 0


def test_report(tmp_path: Path) -> None:
    markdown = write_report("unit", {"summary": {"latence": 2}, "raw_samples": []}, tmp_path)
    data = json.loads((tmp_path / "unit.json").read_text())
    assert data["raw_samples"] == []
    assert data["metadata"]["git_commit"]
    assert data["metadata"]["timestamp_utc"].endswith("+00:00")
    assert "| latence | 2 |" in markdown
    assert (tmp_path / "unit.md").read_text() == markdown


def test_report_error(tmp_path: Path) -> None:
    file = tmp_path / "file"
    file.write_text("occupied")
    with pytest.raises(FileExistsError):
        write_report("unit", {}, file)
