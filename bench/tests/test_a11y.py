import asyncio
import json

import pytest

from bench import a11y
from bench.a11y_session import A11ySession, parse_response


def test_parse_response():
    assert parse_response(b'{"result": null, "latency_ms": 1.2}')["result"] is None
    with pytest.raises(RuntimeError, match="calc_exit"):
        parse_response(b'{"error": "calc_exit:1"}')


@pytest.mark.parametrize(
    "line",
    [
        b"",
        b"nope",
        b"[]",
        b"{}",
        b'{"result": {}}',
        b'{"result": {}, "latency_ms": "bad"}',
        b'{"result": {}, "latency_ms": -1}',
        b'{"result": {}, "latency_ms": NaN}',
        b'{"result": {}, "latency_ms": true}',
    ],
)
def test_parse_response_invalid(line):
    with pytest.raises(ValueError, match="invalide"):
        parse_response(line)


def test_select_targets():
    buttons = [
        {"name": name, "bounds": bounds}
        for name, bounds in [
            ("Bold", [1, 2, 10, 10]),
            ("Gras", [0, 0, 0, 0]),
            ("Italic", [2, 2, 10, 10]),
            ("Other", [0, 0, 10, 10]),
        ]
    ]
    assert a11y.select_targets(buttons) == ["Bold", "Italic"]
    assert a11y.select_targets([]) == []


def test_aggregate_empty_and_errors():
    summary = a11y.summarize([], [{"reason": "timeout"}], [], 2)
    assert summary["failures"] == 1
    assert summary["failure_reasons"] == {"timeout": 1}
    assert summary["snapshot"] == {
        "count": 0,
        "p50_ms": None,
        "p95_ms": None,
        "min_ms": None,
        "max_ms": None,
    }
    assert summary["tree_node_count"] == {"min": None, "max": None}
    assert summary["iterations_completed"] == summary["cell_reads_total"] == 0


def test_aggregate_nominal():
    samples = [
        {
            "iteration": 0,
            "operation": "snapshot",
            "latency_ms": 4.0,
            "result": {"node_count": 5, "max_depth": 2, "roles": {"table": 1}, "truncated": True},
        },
        {"iteration": 0, "operation": "find", "name": "Bold", "latency_ms": 3.0, "result": {}},
        {"iteration": 0, "operation": "read_cell", "latency_ms": 2.0, "result": {"correct": True}},
        {"iteration": 1, "operation": "read_cell", "latency_ms": 6.0, "result": {"correct": False}},
    ]
    summary = a11y.summarize(samples, [], [{"time_to_bus_ms": 10.0, "time_to_window_ms": 12.0}], 2)
    assert summary["read_cell"] == {
        "count": 2,
        "p50_ms": 2.0,
        "p95_ms": 6.0,
        "max_ms": 6.0,
        "min_ms": 2.0,
    }
    assert summary["find_by_name"]["Bold"]["count"] == 1
    assert summary["cell_reads_correct"] == summary["iterations_completed"] == 1
    assert summary["cell_reads_total"] == 2
    assert summary["tree_roles_last"] == {"table": 1}
    assert summary["tree_node_count"] == {"min": 5, "max": 5}
    assert summary["truncated_snapshots"] == 1


@pytest.mark.parametrize(
    "options",
    [{"iterations": 0}, {"timeout": 0}, {"max_nodes": 0}, {"max_depth": 0}, {"plugin": "bad"}],
)
async def test_invalid_options(options):
    with pytest.raises(ValueError):
        await a11y.run(**options)


async def test_session_timeout():
    class Input:
        def write(self, data):
            assert json.loads(data)["op"] == "snapshot"

        async def drain(self):
            pass

    class Output:
        async def readline(self):
            await asyncio.Event().wait()

    class Process:
        stdin = Input()
        stdout = Output()
        returncode = None

    session = A11ySession(timeout=0.01)
    session.process = Process()
    with pytest.raises(TimeoutError):
        await session.request("snapshot")


@pytest.mark.live
async def test_a11y_live():
    report = await a11y.run(iterations=2)
    summary = report["summary"]
    assert summary["failures"] == 0, report["failures"]
    assert summary["snapshot"]["count"] == summary["cell_reads_correct"] == 2
    assert summary["find"]["count"] >= 6
    assert summary["tree_node_count"]["min"] > 10
    assert summary["time_to_bus"]["p50_ms"] > 0
    assert all(
        sample["result"]["bounds"][2] > 0
        for sample in report["raw_samples"]
        if sample["operation"] == "find"
    )
