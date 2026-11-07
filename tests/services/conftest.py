from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RESULTS = Path(__file__).resolve().parent / "results"
_SCHEMAS = {
    p.stem.removesuffix(".schema"): json.loads(p.read_text())
    for p in (ROOT / "contracts").glob("*.schema.json")
}
_REGISTRY = Registry().with_resources(
    (s["$id"], Resource.from_contents(s)) for s in _SCHEMAS.values()
)


# Les clients exigent les extras `holo`, `jev`, `gladia`, `linkup` ; sans eux (CI de base,
# `pip install -e .`) les modules de test du dossier ne sont pas collectés.
SERVICE_DEPS = ("httpx", "h2", "websockets", "openai")
MISSING_DEPS = [m for m in SERVICE_DEPS if importlib.util.find_spec(m) is None]
collect_ignore = (
    ["test_services_unit.py", "test_services_live.py", "test_verify_live.py"]
    if MISSING_DEPS else []
)


@pytest.fixture(autouse=True)
def pace_live_holo(request, monkeypatch):
    if request.node.get_closest_marker("live") is None or MISSING_DEPS:
        return
    from engine.services.holo import HoloCloudClient

    if not hasattr(pace_live_holo, "pacer"):
        Pacer = run_path(str(ROOT / "bench/holo_pacing.py"))["Pacer"]
        pace_live_holo.pacer = Pacer(interval=2.5)
    complete = HoloCloudClient._complete

    async def paced(self, *args, **kwargs):
        await pace_live_holo.pacer.acquire()
        return await complete(self, *args, **kwargs)

    monkeypatch.setattr(HoloCloudClient, "_complete", paced)


def pytest_report_header(config: pytest.Config) -> str | None:
    if MISSING_DEPS:
        return (
            f"tests/services ignorés : {', '.join(MISSING_DEPS)} absents "
            "(pip install -e '.[holo,jev,gladia,linkup]')"
        )
    return None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: appelle réellement un service cloud (clé requise)")


def validate_contract(name: str, message: dict[str, Any]) -> None:
    Draft202012Validator(_SCHEMAS[name], registry=_REGISTRY).validate(message)


def contract_example(name: str, kind: str) -> dict[str, Any]:
    return json.loads(
        (ROOT / "contracts" / "examples" / name / "valid" / f"{kind}.json").read_text()
    )


def require_env(name: str) -> None:
    if not os.environ.get(name):
        pytest.skip(f"{name} absent : test live ignoré")
