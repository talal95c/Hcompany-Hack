"""Profils applicatifs validés, partagés par les clients cloud."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class AppProfile:
    id: str
    name: str
    vocabulary: tuple[str, ...]
    docs_domains: tuple[str, ...]
    jev_context: str
    answer_fields: Mapping[str, str]
    default_sensor: str

    def answer_schema(self) -> dict[str, Any]:
        fields = {
            "answer": f"Short answer for a {self.name} learner",
            "app_version": f"Version of {self.name} the documentation refers to",
            "menu_path": f"Menu path in {self.name}",
            "shortcut": f"Keyboard shortcut in {self.name}",
        }
        fields.update({key: f"{value} ({self.name})" for key, value in self.answer_fields.items()})
        return {
            "type": "object",
            "properties": {
                name: {"type": "string", "description": description}
                for name, description in fields.items()
            },
            "required": ["answer"],
        }


def _apps_dir() -> Path:
    return Path(os.environ.get("HCOMPANY_APPS_DIR", Path(__file__).resolve().parents[2] / "apps"))


@lru_cache(maxsize=128)
def _load(root: Path, app_id: str) -> AppProfile:
    path = root / app_id / "profile.json"
    if not path.is_file():
        if app_id == "generic":
            raise FileNotFoundError(path)
        return _load(root, "generic")
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((root / "profile.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)
    if data["id"] != app_id:
        raise ValueError("profile id must match its folder")
    return AppProfile(
        id=data["id"],
        name=data["name"],
        vocabulary=tuple(data["vocabulary"]),
        docs_domains=tuple(data["docs_domains"]),
        jev_context=data["jev_context"],
        answer_fields=MappingProxyType(data["answer_fields"]),
        default_sensor=data["default_sensor"],
    )


def load_profile(app_id: str | None) -> AppProfile:
    app_id = app_id if app_id and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", app_id) else "generic"
    return _load(_apps_dir().resolve(), app_id)


def profile_for_lesson_app(app: Mapping[str, Any]) -> AppProfile:
    profile = load_profile(app.get("id"))
    if profile.id != app.get("id") and app.get("name"):
        return replace(profile, name=app["name"])
    return profile


def list_profiles() -> list[AppProfile]:
    root = _apps_dir().resolve()
    return [load_profile(path.parent.name) for path in sorted(root.glob("*/profile.json"))]


def profile_for_lesson(lesson: Mapping[str, Any]) -> AppProfile:
    if isinstance(lesson.get("app"), Mapping):
        return profile_for_lesson_app(lesson["app"])
    registry = json.loads((_apps_dir() / "legacy.json").read_text(encoding="utf-8"))
    for field, app_id in registry.items():
        if field in lesson:
            return load_profile(app_id)
    return load_profile(None)
