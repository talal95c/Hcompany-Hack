"""Registre des checks : génériques d'application et espaces applicatifs (`blender.*`)."""

from typing import Any

from engine.checks import blender, generic
from engine.checks.base import CheckResult
from engine.checks.blender import SceneState, close, matches
from engine.checks.generic import AppState, Lookup

NAMESPACES = {"blender": blender}
NAMES = generic.NAMES | blender.NAMES | frozenset(
    f"{space}.{name}" for space, module in NAMESPACES.items() for name in module.NAMES
)


def resolve(name: str) -> tuple[Any, str]:
    """Module de check et nom local ; les noms nus historiques restent ceux de Blender."""
    if name in generic.NAMES:
        return generic, name
    space, _, local = name.partition(".")
    if local and space in NAMESPACES and local in NAMESPACES[space].NAMES:
        return NAMESPACES[space], local
    if name in blender.NAMES:
        return blender, name
    raise ValueError(f"Check inconnu : {name}")


def namespace(name: str) -> str | None:
    module, _ = resolve(name)
    return None if module is generic else next(k for k, v in NAMESPACES.items() if v is module)


def require_check(name: str) -> None:
    resolve(name)


def evaluate(name: str, state: Any, params: dict) -> CheckResult:
    module, local = resolve(name)
    if module is generic:
        return generic.evaluate(local, state, params)
    if not isinstance(state, SceneState):
        return CheckResult("unknown", "Capteur applicatif absent", getattr(state, "revision", -1),
                           0)
    return module.evaluate(local, state, params)


def progress_signature(name: str, state: Any, params: dict) -> str:
    module, local = resolve(name)
    if module is not generic and not isinstance(state, SceneState):
        return "null"
    return module.progress_signature(local, state, params)


__all__ = ["AppState", "CheckResult", "Lookup", "NAMES", "SceneState", "close", "evaluate",
           "matches", "namespace", "progress_signature", "require_check", "resolve"]
