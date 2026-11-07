"""Preuves différentielles et checkpoints : probes déterministes."""

import copy
import json

import pytest

from prep.prover import generic
from prep.prover.generic import drive_step, file_sha256, prove_generic_lesson
from tests.prep.test_generic import FakeDesktop, FakeOperator, compiled, operator_script


@pytest.fixture(autouse=True)
def no_action_delay(monkeypatch):
    async def no_sleep(*args):
        pass

    monkeypatch.setattr(generic.asyncio, "sleep", no_sleep)


async def setup_lesson(tmp_path):
    lesson = await compiled()
    lesson["steps"] = lesson["steps"][:1]
    lesson["steps"][0]["check"]["params"]["timeout_ms"] = 0
    fixture = tmp_path / "initial.json"
    fixture.write_text("{}")
    return lesson, fixture


class CountingDesktop(FakeDesktop):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.snapshots = 0

    async def snapshot(self, *, cells=None):
        self.snapshots += 1
        return await super().snapshot(cells=cells)


@pytest.mark.parametrize("dialog_kind", ["window", "modal"])
async def test_exhaustion_cannot_prove_with_unfinished_wizard(tmp_path, dialog_kind):
    lesson, fixture = await setup_lesson(tmp_path)

    class WizardDesktop(FakeDesktop):
        async def execute(self, action, *, image_size):
            self.state["B6"] = "465"

        async def snapshot(self, *, cells=None):
            packet = await super().snapshot(cells=cells)
            if self.state.get("B6"):
                if dialog_kind == "window":
                    packet["windows"].append("Unfinished wizard")
                else:
                    packet["nodes"].append(
                        {
                            "ref": "wizard",
                            "role": "dialog",
                            "name": "Unfinished wizard",
                            "states": ["visible"],
                        }
                    )
            return packet

    desktop = WizardDesktop(tmp_path)
    await desktop.open(fixture)
    result = await drive_step(
        desktop, FakeOperator(operator_script()), lesson["steps"][0], context="", max_turns=1
    )
    assert result["turns"][0]["open_dialogs"] == ["Unfinished wizard"]
    assert result["check"]["result"] != "pass"
    proven = await prove_generic_lesson(
        lesson,
        WizardDesktop(tmp_path),
        FakeOperator(operator_script()),
        tmp_path / "out",
        fixture=fixture,
        max_turns=1,
    )
    assert proven["status"] != "proven"


async def test_initial_unknown_is_not_a_differential_proof(tmp_path):
    lesson, fixture = await setup_lesson(tmp_path)

    class IncompleteDesktop(FakeDesktop):
        async def snapshot(self, *, cells=None):
            packet = await super().snapshot(cells=cells)
            if not self.state:
                packet["complete"] = False
            return packet

    operator = FakeOperator(operator_script())
    out = tmp_path / "out"
    result = await prove_generic_lesson(
        lesson, IncompleteDesktop(tmp_path), operator, out, fixture=fixture
    )
    evidence = json.loads((out / "proof/sum_sales.json").read_text())
    assert evidence["check_before"]["result"] == "unknown"
    assert result["status"] != "proven" and operator.calls == 0


async def test_reuse_opens_and_observes_checkpoint(tmp_path):
    lesson, fixture = await setup_lesson(tmp_path)
    out = tmp_path / "out"
    first = await prove_generic_lesson(
        lesson, FakeDesktop(tmp_path), FakeOperator(operator_script()), out, fixture=fixture
    )
    assert first["status"] == "proven"
    desktop, operator = CountingDesktop(tmp_path), FakeOperator([])
    result = await prove_generic_lesson(lesson, desktop, operator, out, fixture=fixture)
    assert result["status"] == "proven" and operator.calls == 0
    assert "sum_sales-checkpoint.json" in desktop.opened and desktop.snapshots >= 1
    evidence = json.loads((out / "proof/sum_sales.json").read_text())
    assert evidence["check_replay"]["known_errors"] == [{"code": "partial_range", "result": "fail"}]


async def test_matching_cache_hash_cannot_certify_stale_checkpoint(tmp_path):
    lesson, fixture = await setup_lesson(tmp_path)
    out = tmp_path / "out"
    await prove_generic_lesson(
        lesson, FakeDesktop(tmp_path), FakeOperator(operator_script()), out, fixture=fixture
    )
    checkpoint = out / "proof/sum_sales-checkpoint.json"
    checkpoint.write_text("{}")
    path = out / "proof/sum_sales.json"
    evidence = json.loads(path.read_text())
    evidence["checkpoint_sha256"] = file_sha256(checkpoint)
    path.write_text(json.dumps(evidence))
    desktop = CountingDesktop(tmp_path)
    result = await prove_generic_lesson(lesson, desktop, FakeOperator([]), out, fixture=fixture)
    assert result["status"] != "proven" and desktop.snapshots >= 1
    assert json.loads(path.read_text())["check_replay"]["result"] != "pass"


async def test_changed_error_check_invalidates_reuse(tmp_path):
    lesson, fixture = await setup_lesson(tmp_path)
    out = tmp_path / "out"
    await prove_generic_lesson(
        lesson, FakeDesktop(tmp_path), FakeOperator(operator_script()), out, fixture=fixture
    )
    lesson["steps"][0]["known_errors"][0]["check"] = copy.deepcopy(lesson["steps"][0]["check"])
    operator = FakeOperator(operator_script())
    result = await prove_generic_lesson(
        lesson, FakeDesktop(tmp_path), operator, out, fixture=fixture
    )
    assert operator.calls > 0 and result["status"] != "proven"
    assert json.loads((out / "proof/sum_sales.json").read_text())["mode_trace"][0] == "EXECUTE"


async def test_stale_save_must_be_reopened_and_rejected(tmp_path):
    lesson, fixture = await setup_lesson(tmp_path)

    class StaleSaveDesktop(FakeDesktop):
        async def save(self, checkpoint_out):
            checkpoint_out.write_text("{}")
            return checkpoint_out

    desktop = StaleSaveDesktop(tmp_path)
    out = tmp_path / "out"
    result = await prove_generic_lesson(
        lesson, desktop, FakeOperator(operator_script()), out, fixture=fixture
    )
    evidence = json.loads((out / "proof/sum_sales.json").read_text())
    assert evidence["check_final"]["result"] == "pass"
    assert evidence["check_after_save"] == "fail"
    assert result["status"] != "proven" and "sum_sales-checkpoint.json" in desktop.opened


async def test_reopened_checkpoint_with_dialog_is_not_proven(tmp_path):
    lesson, fixture = await setup_lesson(tmp_path)

    class ReopenWizard(FakeDesktop):
        async def snapshot(self, *, cells=None):
            packet = await super().snapshot(cells=cells)
            if self.opened[-1] == "sum_sales-checkpoint.json":
                packet["windows"].append("Unfinished wizard")
            return packet

    out = tmp_path / "out"
    result = await prove_generic_lesson(
        lesson, ReopenWizard(tmp_path), FakeOperator(operator_script()), out, fixture=fixture
    )
    evidence = json.loads((out / "proof/sum_sales.json").read_text())
    assert result["status"] != "proven"
    assert evidence["checkpoint_verification"]["open_dialogs"] == ["Unfinished wizard"]
