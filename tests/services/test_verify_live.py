"""Recettes live sur captures réelles et fenêtres Xvfb privées, jamais sur :0."""

from __future__ import annotations

import time
from dataclasses import asdict
from urllib.parse import urlsplit

import pytest

from engine.services.computer_use import run_steps
from engine.services.holo import HoloCloudClient
from engine.services.jev import CodivJevClient
from engine.services.latency import LatencyRecorder
from engine.services.linkup import LinkupSearchClient
from engine.services.profiles import load_profile
from engine.services.verify import HoloVerifier
from engine.services.x11 import XdotoolExecutor, capture_x11

from .conftest import FIXTURES, RESULTS, require_env
from .fixtures.make_screens import calc_session

pytestmark = pytest.mark.live

CASES = [
    (
        "calc_sum_formula.png",
        "libreoffice-calc",
        "Cell A4 contains a SUM formula summing A1 through A3.",
        "pass",
    ),
    ("calc_sum_formula.png", "libreoffice-calc", "Cell A4 is empty.", "fail"),
    ("calc_sum_formula.png", "libreoffice-calc", "Cell A1 displays the number 10.", "pass"),
    (
        "calc_no_formula.png",
        "libreoffice-calc",
        "Cell A4 contains a SUM formula summing A1 through A3.",
        "fail",
    ),
    ("calc_no_formula.png", "libreoffice-calc", "Cell A4 is empty.", "pass"),
    ("calc_no_formula.png", "libreoffice-calc", "Cell A1 displays the number 99.", "fail"),
    (
        "blender_torus.png",
        "blender",
        "A torus or donut-shaped object is visible in the 3D viewport.",
        "pass",
    ),
    ("blender_torus.png", "blender", "The selected object in the 3D viewport is a cube.", "fail"),
    ("blender_torus.png", "blender", "A 3D viewport with a grid is visible.", "pass"),
    (
        "blender_cube.png",
        "blender",
        "A torus or donut-shaped object is visible in the 3D viewport.",
        "fail",
    ),
    ("blender_cube.png", "blender", "The selected object in the 3D viewport is a cube.", "pass"),
    ("blender_cube.png", "blender", "A 3D viewport with a grid is visible.", "pass"),
]


async def test_live_verifier_real_screenshots() -> None:
    require_env("HAI_API_KEY")
    rec = LatencyRecorder()
    rows = []
    async with HoloVerifier(recorder=rec) as verifier:
        for filename, app_id, assertion, expected in CASES:
            result = await verifier.verify(
                (FIXTURES / filename).read_bytes(), assertion, profile=load_profile(app_id)
            )
            rows.append(
                {
                    "fixture": filename,
                    "assertion": assertion,
                    "expected": expected,
                    **asdict(result),
                }
            )
    accuracy = sum(row["verdict"] == row["expected"] for row in rows) / len(rows)
    false_passes = [row for row in rows if row["expected"] == "fail" and row["verdict"] == "pass"]
    rec.write_bench(
        RESULTS / "verify.json",
        extra={
            "model": verifier.model,
            "accuracy": accuracy,
            "cases": rows,
            "false_passes": len(false_passes),
            "unknown_counts_as_incorrect": True,
            "pacing_interval_s": 2.5,
        },
    )
    assert not false_passes, false_passes
    assert accuracy >= 0.8, rows


async def test_live_calc_computer_use(monkeypatch) -> None:
    require_env("HAI_API_KEY")
    rec = LatencyRecorder()
    profile = load_profile("libreoffice-calc")
    output = RESULTS / "computer_use"
    output.mkdir(exist_ok=True)
    captures = []
    start = time.perf_counter()
    with calc_session(80) as env:
        monkeypatch.setenv("DISPLAY", env["DISPLAY"])
        monkeypatch.setenv("XDG_RUNTIME_DIR", env["XDG_RUNTIME_DIR"])

        async def capture() -> bytes:
            image = await capture_x11()
            path = output / f"capture_{len(captures):02d}.png"
            path.write_bytes(image)
            captures.append(str(path.relative_to(RESULTS)))
            return image

        async with HoloCloudClient(model="holo4-27b", recorder=rec) as holo:
            async with HoloVerifier(recorder=rec) as verifier:
                result = await run_steps(
                    holo,
                    "In this spreadsheet, enter =SUM(A1:A3) in cell A4 and confirm with Enter. "
                    "Then select cell A4 again so its SUM formula is visible in the formula bar. "
                    "Do not change the numbers 10, 20, 30 in A1:A3.",
                    capture=capture,
                    execute=XdotoolExecutor(),
                    verifier=verifier,
                    success_assertion=(
                        "Cell A4 is selected, displays 60, and the formula bar shows =SUM(A1:A3)."
                    ),
                    profile=profile,
                    max_steps=8,
                )
        (output / "final.png").write_bytes(await capture_x11())
    rec.write_bench(
        RESULTS / "computer_use.json",
        extra={
            **asdict(result),
            "captures": captures,
            "total_latency_ms": (time.perf_counter() - start) * 1000,
            "pacing_interval_s": 2.5,
            "display": ":80",
            "consent": "explicit user request; isolated synthetic test window",
        },
    )
    assert result.status == "success", asdict(result)
    assert result.final is not None and result.final.verdict == "pass"


EXCEL_SENTENCES = [
    ("Comment je fais une RECHERCHEV ?", "question"),
    ("À quoi sert un tableau croisé dynamique dans Excel ?", "question"),
    ("Fais-le pour moi, ajoute la formule SOMME.", "fais_le"),
    ("Remplis cette colonne à ma place, vas-y.", "fais_le"),
    ("J'en ai marre, cette formule ne marche jamais !", "frustration"),
    ("Excel me rend fou, rien ne fonctionne !", "frustration"),
    ("Chut, laisse-moi réfléchir à ma formule.", "chut"),
    ("Arrête de parler s'il te plaît.", "chut"),
    ("Je vais prendre un café.", "other"),
    ("Il fait beau aujourd'hui.", "other"),
]


async def test_live_jev_excel_intents() -> None:
    require_env("CODIV_API_KEY")
    rec = LatencyRecorder()
    rows = []
    async with CodivJevClient(profile=load_profile("excel"), recorder=rec) as jev:
        for utterance, expected in EXCEL_SENTENCES:
            decision = await jev.classify_intent(utterance, context="Leçon de formules Excel")
            rows.append(
                {
                    "text": utterance,
                    "expected": expected,
                    "choice": decision.choice,
                    "probability": decision.probability,
                }
            )
    accuracy = sum(row["expected"] == row["choice"] for row in rows) / len(rows)
    rec.write_bench(RESULTS / "jev_excel.json", extra={"accuracy": accuracy, "cases": rows})
    assert accuracy >= 0.8, rows


async def test_live_linkup_excel_official_sources() -> None:
    require_env("LINKUP_API_KEY")
    rec = LatencyRecorder()
    async with LinkupSearchClient(profile=load_profile("excel"), recorder=rec) as client:
        result = await client.search(
            "How do I use the SUM function in Excel?", domains=("support.microsoft.com",)
        )
    rec.write_bench(
        RESULTS / "linkup_excel.json",
        extra={
            "query": result.query,
            "answer": result.answer,
            "data": dict(result.data or {}),
            "sources": [source.url for source in result.sources],
        },
    )
    assert result.answer and result.answer.strip()
    assert result.sources
    assert all(
        urlsplit(source.url).hostname == "support.microsoft.com" for source in result.sources
    )
