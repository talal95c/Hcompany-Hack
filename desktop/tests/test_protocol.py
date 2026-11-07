import json
import re
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


def test_native_event_names_and_frontend_listeners():
    """Tauri event names are not the dotted engine WebSocket discriminants."""
    desktop = Path(__file__).resolve().parents[1]
    emitted = set()
    for path in (desktop / "src-tauri/src").glob("*.rs"):
        emitted.update(re.findall(r'\.emit\(\s*"([^"]+)"', path.read_text()))
        emitted.update(re.findall(r'\.emit_to\(\s*"guide",\s*"([^"]+)"', path.read_text()))
        emitted.update(re.findall(
            r'guide::show(?:_if_current)?\(\s*app,\s*"([^"]+)"', path.read_text()))
    listened = set(re.findall(r'listen\("([^"]+)"', (desktop / "web/app.js").read_text()))
    assert listened <= emitted
    assert "guide:pointer" in listened
    assert all(re.fullmatch(r"[a-zA-Z0-9_:/-]+", name) for name in emitted | listened)
