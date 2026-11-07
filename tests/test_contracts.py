import importlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
SCHEMA_PATHS = sorted(CONTRACTS.glob("*.schema.json"))
SCHEMAS = {path.stem.removesuffix(".schema"): json.loads(path.read_text()) for path in SCHEMA_PATHS}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)
FIXTURES = sorted((CONTRACTS / "examples").glob("*/*/*.json"))


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_is_draft_2020_12(name: str) -> None:
    schema = SCHEMAS[name]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: str(path.relative_to(CONTRACTS)))
def test_example(path: Path) -> None:
    name, expectation = path.parts[-3:-1]
    assert expectation in {"valid", "invalid"}
    validator = Draft202012Validator(SCHEMAS[name], registry=REGISTRY)
    errors = list(validator.iter_errors(json.loads(path.read_text())))
    if expectation == "valid":
        assert not errors, "\n".join(error.message for error in errors)
    else:
        assert errors, f"La fixture invalide est acceptée : {path}"


def test_fixture_inventory() -> None:
    assert set(SCHEMAS) == {"lesson", "addon-events", "commands", "desktop-ws"}
    assert FIXTURES
    assert set((CONTRACTS / "examples").rglob("*.json")) == set(FIXTURES)
    for name, schema in SCHEMAS.items():
        for expectation in ("valid", "invalid"):
            assert list((CONTRACTS / "examples" / name / expectation).glob("*.json"))
        if "oneOf" in schema:
            types = {
                json.loads(path.read_text())["type"]
                for path in (CONTRACTS / "examples" / name / "valid").glob("*.json")
            }
            assert types == set(schema["properties"]["type"]["enum"])


@pytest.mark.parametrize(
    ("document", "schema_name"),
    [
        ("lecon.md", "lesson"),
        ("evenements-addon.md", "addon-events"),
        ("ordres.md", "commands"),
        ("ws-desktop.md", "desktop-ws"),
    ],
)
def test_documented_examples(document: str, schema_name: str) -> None:
    text = (ROOT / "docs" / "contrats" / document).read_text()
    examples = re.findall(r"```json\n([\s\S]*?)\n```", text)
    assert examples
    for example in examples:
        data = json.loads(example)
        schema = SCHEMAS[schema_name]
        if document == "ordres.md" and "type" not in data:
            schema = schema["$defs"]["result"]
        Draft202012Validator(schema, registry=REGISTRY).validate(data)


@pytest.mark.parametrize(
    "path",
    sorted(
        path
        for package in ("engine", "prep", "agent", "addon")
        for path in (ROOT / package).rglob("__init__.py")
    ),
    ids=lambda path: str(path.relative_to(ROOT)),
)
def test_package_import(path: Path) -> None:
    module = ".".join(path.relative_to(ROOT).parent.parts)
    assert importlib.import_module(module).__name__ == module
