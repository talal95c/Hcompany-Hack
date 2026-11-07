import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.services.errors import QuotaExceeded, ServiceTimeout, ServiceUnavailable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generic_evaluator import Evaluator, matches_value  # noqa: E402
from odf_evidence import inspect_document  # noqa: E402
from prove_generic import prove  # noqa: E402
from visual_capture import png_dimensions, prepare_image, scaled_dimensions  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "lessons/tableur-somme"


def load(path):
    return json.loads(path.read_text())


def validators():
    module = pytest.importorskip("jsonschema")
    return (module.Draft202012Validator(load(ROOT / "contracts/lesson.schema.json")),
            module.Draft202012Validator(load(ROOT / "lessons/generic-steps.schema.json")))


@pytest.mark.parametrize("lesson_id,app_id,app_name,count", [
    ("tableur-somme", "libreoffice-calc", "LibreOffice Calc", 5),
    ("texte-titre", "libreoffice-writer", "LibreOffice Writer", 3),
])
def test_generic_contract_companion_and_evidence(lesson_id, app_id, app_name, count):
    directory = ROOT / "lessons" / lesson_id
    contract, companion_schema = validators()
    lesson, companion = load(directory / "lesson.json"), load(directory / "steps.json")
    contract.validate(lesson)
    companion_schema.validate(companion)
    assert lesson["schema_version"] == "2.0"
    assert lesson["app"] == {"id": app_id, "name": app_name,
                             "version": "7.3.7", "sensor": "auto"}
    assert lesson["revision"] == 1
    assert lesson["language"] == "fr-FR"
    assert len(lesson["steps"]) == count
    assert len({s["why"] for s in lesson["steps"]}) == count
    assert set(companion) == {s["id"] for s in lesson["steps"]}
    assert lesson["source"]["uri"] == f"authored://lessons/{lesson_id}/SOURCE.md"
    assert hashlib.sha256((directory / "SOURCE.md").read_bytes()).hexdigest() == (
        lesson["source"]["sha256"])
    for step in lesson["steps"]:
        assert step["procedure_ref"] == lesson_id + "/" + step["id"]
        assert len(set(companion[step["id"]]["help_ladder"].values())) == 4
        assert all(step["target"].get(field) for field in
                   ["description", "role", "path", "app_region"])
    if lesson["status"] == "draft":
        assert lesson_id == "tableur-somme"
        assert lesson["proof"]["ui_path_verified"] is False
        assert all(s["proof"]["status"] == "draft" for s in lesson["steps"])
        return
    assert lesson["status"] == "proven"
    manifest = load(directory / lesson["proof"]["evidence_ref"])
    required = {"lesson.json", "steps.json", "SOURCE.md"}
    assert required <= manifest["sha256"].keys()
    assert manifest["native_only"] is False
    assert manifest["app_start_seconds"] and min(manifest["app_start_seconds"]) > 0
    for relative, digest in manifest["sha256"].items():
        path = (directory / relative).resolve()
        assert path.is_relative_to(directory.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    for step in lesson["steps"]:
        extra = companion[step["id"]]
        assert step["procedure_ref"] == lesson_id + "/" + step["id"]
        assert step["proof"]["status"] == "proven"
        assert step["proof"]["ui_path_verified"] is True
        target = step["target"]
        assert all(target[field] for field in ["description", "role", "path", "app_region"])
        assert target["app_region"] in target["path"]
        assert len(set(extra["help_ladder"].values())) == 4
        reference = step["proof"]["evidence_ref"]
        required.add(reference)
        assert reference in manifest["sha256"]
        proof = load(directory / reference)
        assert len(proof["artifact_results"]) == len(extra.get("artifact_checks", []))
        for artifact, specification in zip(proof["artifact_results"],
                                            extra.get("artifact_checks", []), strict=True):
            required.add(artifact["evidence_ref"])
            saved = directory / artifact["evidence_ref"]
            result = inspect_document(saved.parent, {**specification, "filename": saved.name})
            assert result["status"] == artifact["status"] == "pass"
            assert result["sha256"] == artifact["sha256"]
            assert result["content_sha256"] == artifact["content_sha256"]
        assert proof["actions"] == extra["expected_actions"]
        assert proof["checks"] == [step["check"], *extra["checks"]]
        assert not all(s == "pass" for s in proof["before_checks"])
        assert all(s == "pass" for s in proof["after_checks"])
        assert "pass" not in proof["known_errors"]
        assert proof["seconds"] > 0
        errors = [*step["known_errors"], *extra["known_errors_extra"]]
        assert errors
        assert [e["code"] for e in errors] == [e["code"] for e in proof["error_proofs"]]
        measurements = [*proof["before_results"], *proof["after_results"]]
        for specification, error in zip(errors, proof["error_proofs"], strict=True):
            assert error["before"] == proof["before"]
            assert error["check"] == specification["check"]
            assert error["actions"] == extra["mistake_actions"][error["code"]]
            assert error["on_mistake"] == "pass"
            assert error["on_correct_path"] != "pass"
            assert not all(s == "pass" for s in error["step_checks_on_mistake"])
            measurements += [error["mistake_result"], error["correct_result"],
                             *error["step_check_results"]]
        for result in measurements:
            assert result["seconds"] > 0
            assert result["read_seconds"] and min(result["read_seconds"]) > 0
            if result["visual"]:
                visual = result["visual"]
                assert visual["image"] in manifest["sha256"]
                assert visual["original_image"] in manifest["sha256"]
                required.update([visual["image"], visual["original_image"]])
                assert png_dimensions(directory / visual["original_image"]) == (
                    visual["original_dimensions"])
                assert png_dimensions(directory / visual["image"]) == visual["sent_dimensions"]
                assert min(visual["sent_dimensions"].values()) >= 600
                assert scaled_dimensions(**visual["original_dimensions"]) == (
                    visual["sent_dimensions"])
                assert visual["seconds"] > 0
                assert visual["model"] == "holo4-27b"
                assert visual["request_id"]
                assert result["status"] == Evaluator.visual_status(visual, {"min_confidence": 0.8})
    assert set(manifest["sha256"]) == required


@pytest.mark.parametrize("invalid", [{}, {"bad": {}}, {"bad": {"unexpected": True}}])
def test_generic_companion_rejects_empty_or_unknown(invalid):
    _, schema = validators()
    assert not schema.is_valid(invalid)


def test_generic_schema_closes_actions_checks_and_metadata():
    _, schema = validators()
    for field in ["goal", "help_ladder", "expected_actions", "checks", "known_errors_extra",
                  "mistake_actions"]:
        companion = load(DIRECTORY / "steps.json")
        del companion["saisir_entete"][field]
        assert not schema.is_valid(companion)
    for replacement in [{"kind": "script", "text": "unsafe"},
                        {"kind": "click", "target": {"description": "x"}, "x": 4},
                        {"kind": "type", "text": ""}]:
        companion = load(DIRECTORY / "steps.json")
        companion["saisir_entete"]["expected_actions"] = [replacement]
        assert not schema.is_valid(companion)
    companion = load(DIRECTORY / "steps.json")
    companion["saisir_entete"]["checks"] = [{"name": "unknown", "params": {}}]
    assert not schema.is_valid(companion)


class FakeReader:
    def __init__(self, nodes=None, complete=True, title="Document"):
        self.nodes = [] if nodes is None else nodes
        self.complete = complete
        self.title = title
        self.reads = 0

    def read(self, target):
        self.reads += 1
        return self.nodes, self.complete

    def window_title(self):
        return self.title


@pytest.mark.parametrize("actual,expected,match,tolerance,result", [
    ("Montant", "Montant", "equals", 0, True),
    ("50,00 €", "€", "contains", 0, True),
    ("A5 = 50", r"^A5 = \d+$", "regex", 0, True),
    (12.001, 12, "equals", 0.01, True), (12.1, 12, "equals", 0.01, False),
    (True, True, "equals", 0, True), (1, True, "equals", 0, False),
    (True, 1, "equals", 0, False), ("12", 12, "equals", 0, False),
    ("", "Montant", "equals", 0, False), (float("nan"), 12, "equals", 1, False),
])
def test_value_matching(actual, expected, match, tolerance, result):
    assert matches_value(actual, expected, match, tolerance) is result


@pytest.mark.parametrize("name,params,nodes,complete,expected", [
    ("element_exists", {}, [{}], True, "pass"),
    ("element_exists", {}, [], True, "fail"),
    ("element_exists", {"present": False}, [], True, "pass"),
    ("element_exists", {"present": False}, [], False, "unknown"),
    ("element_exists", {}, [{}, {}], True, "unknown"),
    ("element_exists", {}, [{}], False, "unknown"),
    ("element_value", {"value": "50"}, [{"value": "50"}], True, "pass"),
    ("element_value", {"value": "50"}, [{"value": "42"}], True, "fail"),
    ("element_value", {"value": "50"}, [{}], True, "unknown"),
    ("element_value", {"value": "50"}, [], True, "fail"),
    ("element_state", {"states": ["checked"]}, [{"states": ["checked"]}], True, "pass"),
    ("element_state", {"states": ["checked"]}, [{"states": []}], True, "fail"),
    ("element_state", {"absent_states": ["checked"]}, [{"states": []}], True, "pass"),
    ("element_state", {"states": ["checked"]}, [{}], True, "unknown"),
    ("element_state", {"absent_states": ["selected"]},
     [{"states": [], "unsupported_states": ["selected"]}], True, "unknown"),
    ("element_state", {}, [{"states": []}], True, "unknown"),
    ("other", {}, [{}], True, "unknown"),
])
def test_generic_statuses(name, params, nodes, complete, expected):
    check = {"name": name, "params": {"target": {"description": "Test"}, **params}}
    result = Evaluator(FakeReader(nodes, complete)).evaluate(check)
    assert result["status"] == expected


def test_timeouts_errors_reconnection_and_window_titles():
    reader = FakeReader([], False)
    check = {"name": "element_exists", "params": {"target": {}, "timeout_ms": 60}}
    assert Evaluator(reader).evaluate(check)["status"] == "unknown"
    assert reader.reads >= 2
    reader.nodes, reader.complete = [{}], True
    assert Evaluator(reader).evaluate(check)["status"] == "pass"
    title = {"name": "window_title", "params": {"value": "Doc"}}
    assert Evaluator(reader).evaluate(title)["status"] == "pass"
    reader.title = None
    assert Evaluator(reader).evaluate(title)["status"] == "unknown"
    reader.title = "Other"
    assert Evaluator(reader).evaluate(title)["status"] == "fail"
    invalid = {"name": "element_value", "params": {"target": {}, "value": "[", "match": "regex"}}
    reader.nodes = [{"value": "x"}]
    assert Evaluator(reader).evaluate(invalid)["status"] == "unknown"


@pytest.mark.parametrize("error", [RuntimeError("Unavailable"), OSError("Disconnected"),
                                  subprocess.TimeoutExpired("reader", 1)])
def test_reader_errors_are_unknown(error):
    class BrokenReader:
        def read(self, target):
            raise error

    check = {"name": "element_exists", "params": {"target": {"description": "Test"}}}
    assert Evaluator(BrokenReader()).evaluate(check)["status"] == "unknown"


@pytest.mark.parametrize("visual,expected", [
    (None, "unknown"), ({"answer": True, "confidence": 0.9}, "pass"),
    ({"answer": False, "confidence": 0.9}, "fail"),
    ({"answer": True, "confidence": 0.7}, "unknown"),
    ({"answer": "yes", "confidence": 1}, "unknown"),
    ({"answer": True, "confidence": float("nan")}, "unknown"),
    ({"answer": True, "confidence": True}, "unknown"),
    ({"answer": True, "confidence": 1.1}, "unknown"),
])
def test_visual_confidence_is_not_success_without_evidence(visual, expected):
    check = {"name": "visual_assert", "params": {"assertion": "Visible ?"}}
    assert Evaluator(FakeReader(), lambda _: visual).evaluate(check)["status"] == expected


@pytest.mark.parametrize("width,height,expected", [
    (375, 198, {"width": 1137, "height": 600}),
    (198, 375, {"width": 600, "height": 1137}),
    (1200, 700, {"width": 1200, "height": 700}),
    (600, 600, {"width": 600, "height": 600}),
])
def test_capture_scaling_preserves_large_images(width, height, expected):
    assert scaled_dimensions(width, height) == expected


@pytest.mark.parametrize("width,height", [(0, 1), (1, 0), (-1, 1)])
def test_capture_scaling_rejects_empty_dimensions(width, height):
    with pytest.raises(ValueError):
        scaled_dimensions(width, height)


def png_header(width, height):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", width, height))


def test_prepare_image_records_actual_original_and_sent_dimensions(tmp_path, monkeypatch):
    original, sent = tmp_path / "original.png", tmp_path / "sent.png"
    original.write_bytes(png_header(375, 198))

    def convert(args, **kwargs):
        assert args == ["convert", str(original), "-resize", "1137x600!", str(sent)]
        assert kwargs == {"check": True, "timeout": 15}
        sent.write_bytes(png_header(1137, 600))

    monkeypatch.setattr("visual_capture.subprocess.run", convert)
    assert prepare_image(original, sent) == {
        "original_dimensions": {"width": 375, "height": 198},
        "sent_dimensions": {"width": 1137, "height": 600},
    }


@pytest.mark.parametrize("data", [b"", b"not a capture", png_header(0, 198)])
def test_invalid_capture_is_not_sent(tmp_path, data):
    original = tmp_path / "original.png"
    original.write_bytes(data)
    with pytest.raises(ValueError):
        prepare_image(original, tmp_path / "sent.png")


async def test_holo_timeout_remains_unknown(tmp_path, monkeypatch):
    pytest.importorskip("openai")
    holo_assert = pytest.importorskip("holo_assert")

    class TimeoutClient:
        def __init__(self, **kwargs):
            assert kwargs == {"model": "holo4-27b"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def _complete(self, operation, timeout, **kwargs):
            assert operation == "visual_assert"
            assert timeout == 12
            raise ServiceTimeout("holo", "simulated timeout")

    monkeypatch.setattr(holo_assert, "HoloCloudClient", TimeoutClient)
    pause = AsyncMock()
    monkeypatch.setattr(holo_assert.asyncio, "sleep", pause)
    image = tmp_path / "sent.png"
    image.write_bytes(png_header(1137, 600))
    result = await holo_assert.evaluate_image({"image": str(image), "assertion": "Visible ?"})
    assert result["error"] == "timeout"
    assert result["seconds"] > 0
    assert len(result["attempts"]) == 5
    assert pause.await_count == 4
    assert all(call.args == (2.5,) for call in pause.await_args_list)
    assert Evaluator.visual_status(result, {}) == "unknown"


@pytest.mark.parametrize("content", ["not JSON", "", "null", "[]", '{"answer":"yes"}'])
async def test_holo_invalid_response_is_not_a_pass(tmp_path, monkeypatch, content):
    pytest.importorskip("openai")
    holo_assert = pytest.importorskip("holo_assert")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def _complete(self, *args, **kwargs):
            return SimpleNamespace(id="fake", choices=[SimpleNamespace(
                message=SimpleNamespace(content=content))])

    monkeypatch.setattr(holo_assert, "HoloCloudClient", FakeClient)
    image = tmp_path / "sent.png"
    image.write_bytes(png_header(1137, 600))
    result = await holo_assert.evaluate_image({"image": str(image), "assertion": "Visible ?"})
    assert result["response"] == content
    assert Evaluator.visual_status(result, {}) == "unknown"


def require_native():
    pytest.importorskip("jsonschema")
    for binary in ["soffice", "Xvfb", "xdotool", "dbus-run-session", "import", "convert",
                   "/usr/bin/python3"]:
        if not shutil.which(binary):
            pytest.skip(f"Dépendance native absente : {binary}")
    probe = subprocess.run(["/usr/bin/python3", "-c", "import pyatspi"], capture_output=True)
    if probe.returncode:
        pytest.skip("pyatspi absent du Python système")


@pytest.mark.parametrize("header,expected_attempts", [("3", 2), ("1000", 1)])
async def test_holo_quota_retry_respects_budget_and_retry_after(monkeypatch, header,
                                                              expected_attempts):
    pytest.importorskip("openai")
    adapter = pytest.importorskip("holo_assert")
    cause = RuntimeError("HTTP 429")
    cause.response = SimpleNamespace(headers={"retry-after": header})
    cause.status_code = 429
    error = QuotaExceeded("holo", "simulated quota")
    error.__cause__ = cause
    call = AsyncMock(side_effect=[error, {"answer": True, "confidence": 1}])
    pause = AsyncMock()
    monkeypatch.setattr(adapter, "assert_image", call)
    monkeypatch.setattr(adapter.asyncio, "sleep", pause)
    result = await adapter.evaluate_image({})
    assert len(result["attempts"]) == call.await_count == expected_attempts
    assert result["attempts"][0]["retry_after"] == header
    if expected_attempts == 2:
        pause.assert_awaited_once_with(3)
        assert Evaluator.visual_status(result, {}) == "pass"
    else:
        pause.assert_not_awaited()
        assert Evaluator.visual_status(result, {}) == "unknown"


async def test_holo_other_service_failure_is_not_retried(monkeypatch):
    pytest.importorskip("openai")
    adapter = pytest.importorskip("holo_assert")
    call = AsyncMock(side_effect=ServiceUnavailable("holo", "simulated failure"))
    monkeypatch.setattr(adapter, "assert_image", call)
    result = await adapter.evaluate_image({})
    assert call.await_count == len(result["attempts"]) == 1
    assert Evaluator.visual_status(result, {}) == "unknown"


def test_holo_retry_after_http_date_and_invalid_header():
    pytest.importorskip("openai")
    adapter = pytest.importorskip("holo_assert")
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=60), usegmt=True)
    assert 58 <= adapter.retry_delay(future) <= 60
    assert adapter.retry_delay("invalid") == adapter.retry_delay(None) == 2.5


def test_odf_extra_evidence_nominal_empty_and_invalid(tmp_path):
    specification = {"filename": "example.odt",
                     "mimetype": "application/vnd.oasis.opendocument.text",
                     "heading": {"text": "Rapport mensuel", "outline_level": 1,
                                 "style_name": "Heading_20_1"}}
    assert inspect_document(tmp_path, specification)["status"] == "fail"
    file = tmp_path / specification["filename"]
    file.write_bytes(b"invalid archive")
    assert inspect_document(tmp_path, specification)["status"] == "unknown"
    content = ('<root xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
               '<text:h text:outline-level="1" text:style-name="Heading_20_1">'
               'Rapport mensuel</text:h></root>')
    with zipfile.ZipFile(file, "w") as archive:
        archive.writestr("mimetype", specification["mimetype"])
        archive.writestr("content.xml", content)
    result = inspect_document(tmp_path, specification)
    assert result["status"] == "pass"
    assert result["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    assert result["content_sha256"] == hashlib.sha256(content.encode()).hexdigest()
    assert inspect_document(tmp_path, {**specification, "heading": {
        **specification["heading"], "text": "Incorrect"}})["status"] == "fail"
    assert inspect_document(tmp_path, {**specification, "filename": "../example.odt"})[
        "status"] == "fail"


@pytest.mark.a11y
@pytest.mark.parametrize("lesson_id,count", [("tableur-somme", 4), ("texte-titre", 3)])
def test_real_accessibility_replay(tmp_path, lesson_id, count):
    require_native()
    directory = tmp_path / lesson_id
    shutil.copytree(ROOT / "lessons" / lesson_id, directory)
    result = prove(directory, tmp_path / "native.json", native_only=True)
    assert len(result["steps"]) == count
    assert load(directory / "lesson.json")["status"] == "draft"
    assert result["native_only"] is True
    assert all(all(s == "pass" for s in step["after_checks"]) for step in result["steps"])


@pytest.mark.a11y
@pytest.mark.live
def test_real_visual_and_accessibility_proof(tmp_path):
    require_native()
    if not os.environ.get("HAI_API_KEY"):
        pytest.skip("HAI_API_KEY absente")
    pytest.importorskip("openai")
    directory = tmp_path / "tableur-somme"
    shutil.copytree(DIRECTORY, directory)
    result = prove(directory, tmp_path / "live.json")
    assert len(result["steps"]) == 5
    assert result["steps"][-1]["after_results"][0]["visual"]["answer"] is True
