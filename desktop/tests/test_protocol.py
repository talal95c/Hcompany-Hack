import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMAS = [json.loads(path.read_text()) for path in CONTRACTS.glob("*.schema.json")]
REGISTRY = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in SCHEMAS)
VALIDATOR = Draft202012Validator(
    json.loads((CONTRACTS / "desktop-ws.schema.json").read_text()), registry=REGISTRY
)


@pytest.mark.parametrize("folder,valid", [("valid", True), ("invalid", False)])
def test_desktop_fixtures_validate_with_jsonschema(folder, valid):
    for path in (CONTRACTS / "examples/desktop-ws" / folder).glob("*.json"):
        assert VALIDATOR.is_valid(json.loads(path.read_text())) is valid, path
