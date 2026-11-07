import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prove import prove  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LESSONS = ROOT / "lessons"
IDS = ["donut", "mini-cube"]


def load(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.mark.parametrize("lesson_id", IDS)
def test_contracts_and_evidence(lesson_id: str) -> None:
    directory = LESSONS / lesson_id
    lesson = load(directory / "lesson.json")
    companion = load(directory / "steps.json")
    Draft202012Validator(load(ROOT / "contracts" / "lesson.schema.json")).validate(lesson)
    Draft202012Validator(load(LESSONS / "steps.schema.json")).validate(companion)
    ids = [step["id"] for step in lesson["steps"]]
    assert len(set(ids)) == len(ids)
    assert set(ids) == set(companion)
    assert lesson["language"] == "fr-FR"
    assert lesson["schema_version"] == "2.0"
    assert lesson["revision"] == 2
    assert lesson["app"] == {
        "id": "blender",
        "name": "Blender",
        "version": "4.5.9",
        "sensor": "addon",
    }
    assert lesson["blender_version"] == "4.5.9"
    assert lesson["status"] == "proven"
    assert len({step["why"] for step in lesson["steps"]}) == len(lesson["steps"])
    assert (
        lesson["source"]["sha256"]
        == hashlib.sha256((directory / "SOURCE.md").read_bytes()).hexdigest()
    )
    assert lesson["source"]["uri"] == f"authored://lessons/{lesson_id}/SOURCE.md"
    manifest = load(directory / lesson["proof"]["evidence_ref"])
    for relative, digest in manifest["sha256"].items():
        assert hashlib.sha256((directory / relative).read_bytes()).hexdigest() == digest
    for step in lesson["steps"]:
        assert step["skill_id"] in lesson["skills"]
        assert step["procedure_ref"] == f"{lesson_id}/{step['id']}"
        proof = load(directory / step["proof"]["evidence_ref"])
        assert not all(value == "pass" for value in proof["before_checks"])
        assert all(value == "pass" for value in proof["after_checks"])
        assert "pass" not in proof["known_errors"]
        assert proof["actions"] == companion[step["id"]]["expected_actions"]
        error_specs = [*step["known_errors"], *companion[step["id"]]["known_errors_extra"]]
        assert companion[step["id"]]["known_errors_extra"]
        assert [error["code"] for error in proof["error_proofs"]] == [
            error["code"] for error in error_specs
        ]
        for error in proof["error_proofs"]:
            assert error["on_mistake"] == "pass"
            assert error["on_correct_path"] != "pass"
            assert not all(result == "pass" for result in error["step_checks_on_mistake"])
            assert error["before"] == proof["before"]
        assert len(set(companion[step["id"]]["help_ladder"].values())) == 4
        assert step["proof"]["ui_path_verified"] is False
    assert manifest["blender_wall_seconds"] > 0


@pytest.mark.parametrize("lesson_id", IDS)
@pytest.mark.parametrize("app", [None, {}, {"id": "blender", "name": "Blender",
                                         "version": "4.5.9", "sensor": "invalid"}])
def test_v2_rejects_missing_empty_or_invalid_app(lesson_id: str, app: dict | None) -> None:
    lesson = load(LESSONS / lesson_id / "lesson.json")
    if app is None:
        del lesson["app"]
    else:
        lesson["app"] = app
    with pytest.raises(ValidationError):
        Draft202012Validator(load(ROOT / "contracts" / "lesson.schema.json")).validate(lesson)


def test_strict_sidecar_rejects_empty_unknown_and_extra() -> None:
    validator = Draft202012Validator(load(LESSONS / "steps.schema.json"))
    for invalid in [{}, {"bad": {}}, {"bad": {"unexpected": 1}}]:
        with pytest.raises(ValidationError):
            validator.validate(invalid)
    valid = load(LESSONS / "mini-cube" / "steps.json")
    valid["add_cube"]["expected_actions"][0]["properties"]["unsafe"] = True
    with pytest.raises(ValidationError):
        validator.validate(valid)


def test_vocabulary() -> None:
    forbidden = "".join(map(chr, [114, 101, 115, 116, 101, 112]))
    for directory in [LESSONS, ROOT / "tests" / "lessons"]:
        for path in directory.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                assert forbidden.encode() not in path.read_bytes().lower(), path


@pytest.mark.blender
@pytest.mark.parametrize("lesson_id", IDS)
def test_real_blender(lesson_id: str, tmp_path: Path) -> None:
    if shutil.which("blender") is None:
        pytest.skip("Blender est introuvable")
    directory = tmp_path / lesson_id
    shutil.copytree(LESSONS / lesson_id, directory)
    result = prove(directory, tmp_path / "result.json")
    assert len(result["steps"]) == (9 if lesson_id == "donut" else 3)
    assert result["negative_cases"] == {
        "empty_scene": "fail",
        "cube_instead_of_torus": "unknown",
        "known_error_cube": "pass",
        "renamed_cube": "unknown",
        "untracked_mesh": "unknown",
        "wrong_subdivision": "fail",
        "broken_topology": "unknown",
    }
    assert all(all(value == "pass" for value in step["after_checks"]) for step in result["steps"])
