"""Chaîne générique réelle : Calc sous Xvfb + AT-SPI, Holo, Linkup."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from statistics import median

import jsonschema
import pytest

from prep.__main__ import parser, prepare
from prep.apps import get_profile
from tests.prep.ods_assertions import assert_tutorial_ods

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).with_name("fixtures") / "calc"
HAS_CALC = bool(shutil.which("soffice") and shutil.which("Xvfb") and shutil.which("xdotool"))
HAS_ATSPI = Path("/usr/lib/python3/dist-packages/pyatspi").exists()
needs_calc = pytest.mark.skipif(not (HAS_CALC and HAS_ATSPI), reason="Calc/AT-SPI absents")


@needs_calc
async def test_calc_sandbox_accessibility_snapshot():
    from prep.sandbox.desktop import DesktopSandbox
    from prep.ui_map.accessibility import build_ui_map, find_nodes

    async with DesktopSandbox(get_profile("libreoffice-calc")) as sandbox:
        fixture = await sandbox.prepare_fixture(FIXTURES / "ventes.csv")
        await sandbox.open(fixture)
        snapshot = await sandbox.snapshot(cells=["A1", "B5"])
        assert snapshot["complete"] and snapshot["windows"]
        assert find_nodes(snapshot, {"role": "cell", "name": "B5"})[0]["value"] == "110"
        ui_map = build_ui_map(snapshot, app={"id": "libreoffice-calc"})
        assert any(c["name"] == "Bold" for c in ui_map["controls"])
        await sandbox.key(["ctrl", "b"])
        bold = find_nodes(await sandbox.snapshot(), {"role": "toggle_button", "name": "Bold"})
        assert "checked" in bold[0]["states"]
        saved = await sandbox.save(sandbox.root / "out.ods")
        assert saved.stat().st_size > 0


@pytest.mark.live
@needs_calc
@pytest.mark.skipif(not os.environ.get("HAI_API_KEY"), reason="HAI_API_KEY absent")
async def test_live_calc_tutorial_to_proven_lesson(tmp_path):
    out = tmp_path / "calc-ventes"
    args = parser().parse_args(
        [
            str(FIXTURES / "tutorial.txt"),
            "--app",
            "libreoffice-calc",
            "--fixture",
            str(FIXTURES / "ventes.csv"),
            "--out",
            str(out),
            "--language",
            "en",
        ]
    )
    assert await prepare(args) == 0
    lesson = json.loads((out / "lesson.json").read_text())
    jsonschema.validate(lesson, json.loads((ROOT / "contracts/lesson.schema.json").read_text()))
    assert lesson["status"] == "proven" and lesson["app"]["id"] == "libreoffice-calc"
    assert len(lesson["steps"]) == 3
    assert {s["check"]["name"] for s in lesson["steps"]} == {
        "calc.cell_formula",
        "calc.range_bold",
        "calc.chart_source",
    }
    manifest = json.loads((out / "proof/manifest.json").read_text())
    accessibility_proofs = []
    for path, digest in manifest["artifacts_sha256"].items():
        assert hashlib.sha256((out / path).read_bytes()).hexdigest() == digest
    for step in lesson["steps"]:
        evidence = json.loads((out / step["proof"]["evidence_ref"]).read_text())
        assert evidence["check_before"]["result"] == "fail"
        assert evidence["attempts"][-1]["check"]["result"] == "pass"
        runtime = evidence["check_final"]["runtime_check"]
        if runtime["sensor"] == "accessibility":
            assert runtime["result"] == "pass" and runtime["snapshot_complete"]
            accessibility_proofs.append(step["id"])
        print(
            "Holo step latencies (s):",
            step["id"],
            [
                turn["holo_duration"]
                for attempt in evidence["attempts"]
                for turn in attempt["turns"]
            ],
        )
    assert accessibility_proofs
    timings = json.loads((out / "timings.json").read_text())
    assert timings["holo_operator"] and timings["sandbox"]
    last = lesson["steps"][-1]["id"]
    saved = out / f"proof/{last}-checkpoint.ods"
    for snippet in assert_tutorial_ods(saved):
        print(snippet)
    holo = [item["duration"] for item in timings["holo_operator"] if "duration" in item]
    atspi = [
        item["duration"] for item in timings["sandbox"] if item["operation"] == "a11y_snapshot"
    ]
    print("Calc artifact:", saved)
    print(
        "Calc measured latencies (s):",
        json.dumps(
            {
                "total": timings["total"],
                "compile": timings["compile"],
                "prove": timings["prove"],
                "holo_median": median(holo),
                "atspi_median": median(atspi),
            }
        ),
    )


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("LINKUP_API_KEY"), reason="LINKUP_API_KEY absent")
async def test_live_app_docs_search():
    from prep.docs_search import search_docs

    results = await search_docs("LibreOffice Calc SUM function", domains=("help.libreoffice.org",))
    assert results and all(r["url"].startswith("https://help.libreoffice.org/") for r in results)


@pytest.mark.live
@needs_calc
@pytest.mark.skipif(not os.environ.get("HAI_API_KEY"), reason="HAI_API_KEY absent")
async def test_live_visual_assert_on_calc():
    from prep.prover.checks import evaluate_check
    from prep.prover.holo_desktop import HoloDesktopAgent
    from prep.sandbox.desktop import DesktopSandbox

    async with DesktopSandbox(get_profile("libreoffice-calc")) as sandbox:
        await sandbox.open(await sandbox.prepare_fixture(FIXTURES / "ventes.csv"))
        async with HoloDesktopAgent() as judge:
            yes = {"name": "visual_assert", "params": {"assertion": "Is a spreadsheet visible?"}}
            no = {"name": "visual_assert", "params": {"assertion": "Is a bar chart visible?"}}
            assert (await evaluate_check(yes, sandbox, judge))["result"] == "pass"
            assert (await evaluate_check(no, sandbox, judge))["result"] in {"fail", "unknown"}
