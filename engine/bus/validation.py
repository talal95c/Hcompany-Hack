"""Validation stricte des contrats, y compris leurs références croisées."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMAS = {p.name: json.loads(p.read_text()) for p in CONTRACTS.glob("*.schema.json")}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)
VALIDATORS = {
    name.removesuffix(".schema.json"): Draft202012Validator(schema, registry=REGISTRY)
    for name, schema in SCHEMAS.items()
}


def validate(kind: str, message: dict) -> None:
    VALIDATORS[kind].validate(message)
