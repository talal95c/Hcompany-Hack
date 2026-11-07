"""Les checks Calc portent sur les cellules/formules/plages enregistrées."""

import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.services.protocols import HoloAction
from prep.apps import get_profile
from prep.apps.calc import NS, CalcAdapter, evaluate_document
from prep.compile.generic import GenericCompiler, _system_prompt
from prep.prover import generic
from prep.sandbox.desktop import DesktopSandbox
from tests.prep.test_generic import (
    APP,
    FakeDesktop,
    FakeOperator,
    HoloStub,
    build_ui_map,
    raw_lesson,
    snapshot,
    transcript,
)


def ods(*, bold_a=True, bold_b=True, range_end="B5", formula="of:=SUM([.B2:.B5])", value="465"):
    namespaces = " ".join(f'xmlns:{prefix}="{uri}"' for prefix, uri in NS.items())

    def cell(bold):
        return f'<table:table-cell table:style-name="{"bold" if bold else "plain"}"/>'

    content = f'''<office:document-content {namespaces}>
      <office:automatic-styles><style:style style:name="bold" style:family="table-cell"
      style:parent-style-name="base"/><style:style style:name="base" style:family="table-cell">
      <style:text-properties fo:font-weight="bold"/></style:style>
      <style:style style:name="plain" style:family="table-cell"/></office:automatic-styles>
      <office:body><office:spreadsheet><table:table table:name="ventes">
      <table:table-row>{cell(bold_a)}{cell(bold_b)}</table:table-row>
      <table:table-row table:number-rows-repeated="4"><table:table-cell/></table:table-row>
      <table:table-row><table:table-cell/><table:table-cell table:formula="{formula}"
      office:value="{value}"/></table:table-row>
      <table:shapes><draw:frame><draw:object xlink:href="./Object 1"/></draw:frame></table:shapes>
      </table:table></office:spreadsheet></office:body></office:document-content>'''
    chart = f"""<office:document-content {namespaces}><chart:chart><chart:plot-area
       table:cell-range-address="ventes.A1:ventes.{range_end}"/></chart:chart></office:document-content>"""
    styles = f"<office:document-styles {namespaces}/>"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("content.xml", content)
        archive.writestr("styles.xml", styles)
        archive.writestr("Object 1/content.xml", chart)
    return output.getvalue()


CHECKS = [
    {
        "name": "calc.cell_formula",
        "params": {"sheet": "ventes", "cell": "B6", "formula": "=SUM(B2:B5)", "value": 465},
    },
    {"name": "calc.range_bold", "params": {"sheet": "ventes", "range": "A1:B1"}},
    {"name": "calc.chart_source", "params": {"sheet": "ventes", "range": "A1:B5"}},
]


@pytest.mark.parametrize("check", CHECKS)
def test_document_checks_nominal_and_malformed(check):
    assert evaluate_document(check, ods())["result"] == "pass"
    assert evaluate_document(check, b"")["result"] == "unknown"
    assert evaluate_document(check, b"not an ODS")["result"] == "unknown"


@pytest.mark.parametrize("bold_a,bold_b", [(False, False), (True, False), (False, True)])
def test_each_header_cell_must_be_bold(bold_a, bold_b):
    assert evaluate_document(CHECKS[1], ods(bold_a=bold_a, bold_b=bold_b))["result"] == "fail"


def test_chart_must_not_include_total_row():
    assert evaluate_document(CHECKS[2], ods(range_end="B6"))["result"] == "fail"


def test_formula_and_value_are_both_required():
    assert evaluate_document(CHECKS[0], ods(formula="", value="465"))["result"] == "fail"
    assert evaluate_document(CHECKS[0], ods(value="355"))["result"] == "fail"
    assert evaluate_document(CHECKS[0], ods(formula="of:=SUM([.B2:.B4])"))["result"] == "fail"


def test_empty_document_is_fail_not_pass():
    data = ods()
    result = evaluate_document(
        {"name": "calc.range_bold", "params": {"sheet": "ventes", "range": "A20:B20"}}, data
    )
    assert result["result"] == "fail"
    assert (
        evaluate_document(
            {"name": "calc.range_bold", "params": {"sheet": "absente", "range": "A1:B1"}}, data
        )["result"]
        == "unknown"
    )


async def test_calc_compiler_rejects_toolbar_success():
    raw = raw_lesson()
    compiler = GenericCompiler(get_profile("libreoffice-calc"), client=HoloStub([json.dumps(raw)]))
    lesson = await compiler.compile(
        transcript(), build_ui_map(snapshot(), app=APP), lesson_id="outcome", app_version="7.3.7.2"
    )
    assert lesson["steps"][1]["proof"]["method"] == "handoff"
    assert "bold_header" in compiler.rejections


async def test_calc_compiler_preserves_exact_outcomes():
    raw = raw_lesson()
    raw["steps"][0]["check"] = CHECKS[0]
    raw["steps"][1]["check"] = CHECKS[1]
    compiler = GenericCompiler(get_profile("libreoffice-calc"), client=HoloStub([json.dumps(raw)]))
    lesson = await compiler.compile(
        transcript(), build_ui_map(snapshot(), app=APP), lesson_id="outcome", app_version="7.3.7.2"
    )
    assert not compiler.rejections
    assert [step["check"] for step in lesson["steps"]] == CHECKS[:2]


def test_compiler_uses_real_sheet_names_and_rejects_invented_sheet():
    profile = get_profile("libreoffice-calc")
    ui_map = {"controls": [], "managed_containers": [{"role": "table", "name": "Sheet ventes"}]}
    assert "['ventes']" in _system_prompt(profile, "7.3", ui_map, None)
    CalcAdapter.validate_success(CHECKS[0], ui_map)
    with pytest.raises(ValueError, match="feuille"):
        CalcAdapter.validate_success(
            {"name": "calc.cell_formula", "params": {**CHECKS[0]["params"], "sheet": "Sheet1"}},
            ui_map,
        )


def name_box(value="A1", *, complete=True, count=1):
    return {
        "complete": complete,
        "nodes": [
            {"ref": "toolbar", "role": "tool bar", "name": "Formula Tool Bar", "states": []},
            *[
                {
                    "ref": f"box{i}",
                    "parent_ref": "toolbar",
                    "role": "text",
                    "name": "",
                    "states": ["editable"],
                    "value": value,
                }
                for i in range(count)
            ],
        ],
    }


@pytest.mark.parametrize(
    "check,selection", [(CHECKS[0], "B6"), (CHECKS[1], "A1:B1"), (CHECKS[2], "A1:B5")]
)
async def test_prepare_step_injects_no_input(check, selection):
    sandbox = SimpleNamespace(
        snapshot=AsyncMock(), focus_text=AsyncMock(), type_text=AsyncMock(), key=AsyncMock()
    )
    context = await CalcAdapter(sandbox).prepare_step(check)
    for mock in (sandbox.snapshot, sandbox.focus_text, sandbox.type_text, sandbox.key):
        mock.assert_not_awaited()
    assert f"ventes.{selection}" in context and "yourself" in context


async def test_document_read_discards_uncommitted_edit_before_saving(tmp_path, monkeypatch):
    sandbox = DesktopSandbox(get_profile("libreoffice-calc"))
    path = tmp_path / "saved.ods"
    path.write_bytes(ods())
    sandbox._document = path
    run = AsyncMock()
    monkeypatch.setattr(sandbox, "_run", run)
    monkeypatch.setattr(generic.asyncio, "sleep", AsyncMock())
    try:
        await sandbox.type_text("=SUM(B2:B5)")
        await sandbox.document_snapshot()
        chords = [call.args[-1] for call in run.await_args_list[1:]]
        assert chords == ["Escape", "ctrl+s"]
        assert [i["purpose"] for i in sandbox.harness_inputs] == [
            "discard_uncommitted_edit",
            "save_for_document_check",
        ]
    finally:
        await sandbox.close()


async def test_reopened_document_is_read_without_resaving(tmp_path, monkeypatch):
    sandbox = DesktopSandbox(get_profile("libreoffice-calc"))
    path = tmp_path / "saved.ods"
    path.write_bytes(ods())
    sandbox._document = path
    run = AsyncMock()
    monkeypatch.setattr(sandbox, "_run", run)
    monkeypatch.setattr(generic.asyncio, "sleep", AsyncMock())
    try:
        assert await sandbox.document_snapshot() == path.read_bytes()
        run.assert_not_awaited()
        await sandbox.key(["ctrl", "b"])
        await sandbox.document_snapshot()
        assert run.await_count == 3
        await sandbox.document_snapshot()
        assert run.await_count == 3
    finally:
        await sandbox.close()


async def test_document_outcome_is_read_only_after_done(tmp_path, monkeypatch):
    class OutcomeDesktop(FakeDesktop):
        async def evaluate_app_check(self, check):
            return {"result": "pass" if self.state.get("bold") else "fail", "sensor": "document"}

    monkeypatch.setattr(generic.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(generic, "visual_dialogs", AsyncMock(return_value=[]))
    operator = FakeOperator([HoloAction("key", keys=("ctrl", "b"))])
    result = await generic.drive_step(
        OutcomeDesktop(tmp_path),
        operator,
        {"instruction": "Mettre en gras", "target": {"description": "En-tête"}, "check": CHECKS[1]},
        context="",
        max_turns=10,
    )
    assert result["check"]["result"] == "pass"
    assert operator.calls == 2
    assert "check_after_action" not in result["turns"][0]
    assert result["turns"][1]["check_after_done"] == "pass"
