"""Sondes de sécurité du capteur et de la preuve générique."""

import copy
import json
import sys

import pytest

from prep.apps import get_profile
from prep.prover.checks import evaluate_check, evaluate_snapshot
from prep.prover.generic import drive_step
from prep.prover.holo_desktop import HoloAction
from prep.sandbox.desktop import DesktopSandbox, scrubbed_env
from tests.prep.test_generic import FakeDesktop, FakeOperator, Judge, Observer, snapshot


def worker_packet():
    packet = copy.deepcopy(snapshot())
    packet.pop("platform", None)
    packet.pop("api", None)
    packet["nodes"] = [
        node for node in packet["nodes"] if node["bounds"]["w"] > 0 and node["bounds"]["h"] > 0
    ]
    return packet


async def test_child_environment_is_allowlisted(monkeypatch):
    credentials = {
        name: "credential-sentinel"
        for name in (
            "SUPABASE_DB_PASSWORD",
            "SUPABASE_SERVICE_ROLE_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "SESSION_COOKIE",
            "XDG_SECRET",
            "AT_SPI_TOKEN",
        )
    }
    for key, value in credentials.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LANG", "C.UTF-8")
    sandbox = DesktopSandbox(get_profile("libreoffice-calc"))
    try:
        sandbox.env = scrubbed_env({**credentials, "DISPLAY": ":99"})
        child = json.loads(
            await sandbox._run(
                sys.executable, "-c", "import os,json; print(json.dumps(dict(os.environ)))"
            )
        )
        assert not credentials.keys() & child.keys()
        assert child["DISPLAY"] == ":99" and child["LANG"] == "C.UTF-8"
        assert "PATH" in child
    finally:
        await sandbox.close()


@pytest.mark.parametrize("damage", ["bounds", "nodes", "complete", "windows", "json"])
async def test_invalid_worker_packet_is_unknown(monkeypatch, damage):
    packet = worker_packet()
    if damage == "bounds":
        del packet["nodes"][0]["bounds"]
    elif damage == "nodes":
        packet["nodes"] = [None]
    elif damage == "complete":
        packet["complete"] = "true"
    elif damage == "windows":
        packet["windows"] = [1]
    raw = b"not json" if damage == "json" else json.dumps(packet).encode()
    sandbox = DesktopSandbox(get_profile("libreoffice-calc"))

    async def worker(*args, **kwargs):
        return raw

    monkeypatch.setattr(sandbox, "_run", worker)
    try:
        result = await sandbox.snapshot()
        assert result["complete"] is False and result["nodes"] == []
        assert result["error"]["code"] == "INVALID_PACKET"
    finally:
        await sandbox.close()


async def test_valid_and_empty_worker_packets(monkeypatch):
    sandbox = DesktopSandbox(get_profile("libreoffice-calc"))
    packet = worker_packet()

    async def worker(*args, **kwargs):
        return json.dumps(packet).encode()

    monkeypatch.setattr(sandbox, "_run", worker)
    try:
        assert (await sandbox.snapshot())["nodes"] == packet["nodes"]
        packet = {"complete": True, "nodes": [], "windows": []}
        assert (await sandbox.snapshot())["nodes"] == []
    finally:
        await sandbox.close()


@pytest.mark.parametrize(
    "name,params",
    [
        ("element_state", {"states": ["enabled"]}),
        ("element_value", {"value": "ready"}),
        ("element_exists", {}),
        ("window_title", {"value": "Ready", "match": "equals"}),
    ],
)
def test_incomplete_and_identical_ambiguous_matches_never_pass(name, params):
    node = {
        "ref": "a",
        "role": "toggle_button",
        "name": "Ready",
        "value": "ready",
        "states": ["enabled"],
        "bounds": {"x": 0, "y": 0, "w": 10, "h": 10},
    }
    check = {
        "name": name,
        "params": {"target": {"role": "toggle_button", "name": "Ready"}, **params},
    }
    packet = {"complete": True, "nodes": [node], "windows": ["Ready"]}
    assert evaluate_snapshot(check, packet)["result"] == "pass"
    assert evaluate_snapshot(check, {**packet, "complete": False})["result"] == "unknown"
    if name != "window_title":
        packet["nodes"].append({**node, "ref": "b"})
        result = evaluate_snapshot(check, packet)
        assert result["result"] == "unknown" and result["match_count"] == 2


@pytest.mark.parametrize(
    "name,params",
    [
        ("element_state", {"absent_states": ["busy"]}),
        ("element_state", {"states": ["enabled"], "absent_states": ["busy"]}),
        ("element_value", {"value": 42, "tolerance": 0.1}),
        ("element_value", {"value": "ready", "match": "contains"}),
        ("element_value", {"value": "^ready$", "match": "regex"}),
        ("window_title", {"value": "Ready", "match": "equals"}),
        ("window_title", {"value": "^Ready$", "match": "regex"}),
    ],
)
async def test_exact_check_is_not_silently_replaced_by_vision(name, params):
    check = {
        "name": name,
        "params": {"target": {"role": "toggle_button", "name": "Ready"}, **params},
    }
    observer = Observer({"complete": False, "nodes": [], "error": {"code": "APP_NOT_FOUND"}})

    class ForbiddenJudge(Judge):
        async def assert_visual(self, *args, **kwargs):
            raise AssertionError("Vision non autorisée")

    result = await evaluate_check(check, observer, ForbiddenJudge("yes", 1), wait_for_pass=False)
    assert result["result"] == "unknown" and result["sensor"] == "accessibility"


async def test_prover_does_not_invent_fallback(tmp_path):
    class LostDesktop(FakeDesktop):
        async def snapshot(self, *, cells=None):
            return {
                "complete": False,
                "nodes": [],
                "windows": [],
                "error": {"code": "APP_NOT_FOUND"},
            }

    step = {
        "instruction": "Attendre",
        "target": {"description": "Ready toggle"},
        "check": {
            "name": "element_state",
            "params": {
                "target": {"name": "Ready", "role": "toggle_button"},
                "absent_states": ["busy"],
                "timeout_ms": 1,
            },
        },
    }
    result = await drive_step(
        LostDesktop(tmp_path), FakeOperator([HoloAction("done")]), step, context="", max_turns=1
    )
    assert result["check"]["result"] == "unknown"
