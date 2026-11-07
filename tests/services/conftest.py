from __future__ import annotations

import json
import os
from pathlib import Path
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
