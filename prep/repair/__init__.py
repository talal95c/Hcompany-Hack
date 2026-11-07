"""Demandes de réparation locales, sans appel réseau."""

import hashlib
import json
from pathlib import Path


def write_repair_request(
    out: Path,
    *,
    lesson_id: str,
    step_id: str,
    reason: str,
    fixture: str,
    expected_result: dict,
    blender_version: str,
) -> Path:
    root = out / "repair"
    root.mkdir(parents=True, exist_ok=True)
    identifier = hashlib.sha256(f"{lesson_id}/{step_id}".encode()).hexdigest()[:20]
    path = root / f"{identifier}.json"
    path.write_text(
        json.dumps(
            {
                "lesson_id": lesson_id,
                "step_id": step_id,
                "reason": reason,
                "contract_ref": (
                    "contracts/lesson.schema.json#/properties/steps/items/properties/check"
                ),
                "fixture": fixture,
                "expected_result": expected_result,
                "blender_version": blender_version,
            },
            indent=2,
        )
    )
    return path
