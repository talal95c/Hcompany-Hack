"""Checks génériques d'application (arbre d'accessibilité, titre, assertion visuelle).

Les lectures viennent d'un `AppState` alimenté par le capteur actif ; un arbre incomplet,
une cible ambiguë ou un verdict visuel incertain donnent `unknown`, jamais `pass`.
"""

import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from engine.checks.base import DETAILS, CheckResult
from engine.interfaces import VerifyResult

NAMES = frozenset({"element_exists", "element_value", "element_state", "window_title",
                   "visual_assert"})
QUERY_FIELDS = ("role", "name", "path")
MAX_PATTERN = 300


@dataclass(frozen=True)
class Lookup:
    """Réponse `a11y.result` à une requête `find` : refs locales au snapshot."""

    nodes: tuple[dict, ...]
    complete: bool
    snapshot_id: str | None
    error: str | None = None

    @property
    def unique(self) -> dict | None:
        return self.nodes[0] if len(self.nodes) == 1 and not self.error else None


@dataclass
class AppState:
    lookups: dict[str, Lookup] = field(default_factory=dict)
    verdicts: dict[str, VerifyResult] = field(default_factory=dict)
    window_title: str | None = None
    app_id: str | None = None
    revision: int = -1
    latest_revision: int = -1
    complete: bool = False

    @property
    def recent(self) -> bool:
        return self.complete and self.revision == self.latest_revision

    @property
    def has_content(self) -> bool:
        return any(lookup.nodes for lookup in self.lookups.values())

    def facts(self) -> dict[str, str | None]:
        return {"window_title": self.window_title}


def query_for(target: dict | None) -> dict | None:
    """Requête a11y dérivée d'une cible descriptive ; None si la cible n'est que visuelle."""
    if not target:
        return None
    query = {key: target[key] for key in QUERY_FIELDS if target.get(key)}
    return query or None


def query_key(query: dict) -> str:
    return json.dumps(query, sort_keys=True, ensure_ascii=False)


def assertion_key(params: dict) -> str:
    return json.dumps({"assertion": params["assertion"], "region": params.get("region")},
                      sort_keys=True, ensure_ascii=False)


def text_matches(actual: str, expected: str, mode: str) -> bool | None:
    if mode == "equals":
        return actual.strip() == expected.strip()
    if mode == "contains":
        return expected.casefold() in actual.casefold()
    if len(expected) > MAX_PATTERN:
        return None
    try:
        return re.search(expected, actual) is not None
    except re.error:
        return None


def parse_number(text: str) -> float | None:
    cleaned = text.strip().replace("\u00a0", "").replace(" ", "")
    if cleaned.count(",") == 1 and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def value_matches(node: dict, params: dict) -> bool | None:
    actual = node.get("value")
    if actual is None:
        return None
    expected: Any = params["value"]
    mode = params.get("match", "equals")
    if isinstance(expected, bool):
        lowered = actual.strip().casefold()
        if lowered in {"true", "1", "vrai"}:
            return expected
        if lowered in {"false", "0", "faux"}:
            return not expected
        return None
    if isinstance(expected, int | float) and mode == "equals":
        number = parse_number(actual)
        if number is None:
            return False
        return abs(number - float(expected)) <= params.get("tolerance", 0)
    return text_matches(actual, str(expected), mode)


def lookup(state: AppState, target: dict) -> Lookup | None:
    query = query_for(target)
    return state.lookups.get(query_key(query)) if query else None


def _evaluate(name: str, state: AppState, params: dict) -> bool | None:
    if name == "window_title":
        if state.window_title is None:
            return None
        return text_matches(state.window_title, params["value"], params.get("match", "contains"))
    if name == "visual_assert":
        verdict = state.verdicts.get(assertion_key(params))
        if verdict is None or verdict.answer is None or verdict.confidence is None:
            return None
        if not math.isfinite(verdict.confidence):
            return None
        return verdict.answer if verdict.confidence >= params.get("min_confidence", 0.8) else None
    found = lookup(state, params["target"])
    if found is None or found.error or not found.complete:
        return None
    if name == "element_exists":
        if found.nodes:
            return params.get("present", True)
        return None if not found.complete else not params.get("present", True)
    node = found.unique
    if node is None:
        return None if found.nodes or not found.complete else False
    if name == "element_value":
        return value_matches(node, params)
    states = set(node.get("states", ()))
    return set(params.get("states", ())) <= states and not states & set(
        params.get("absent_states", ()))


def evaluate(name: str, state: Any, params: dict) -> CheckResult:
    if name not in NAMES:
        raise ValueError(f"Check générique inconnu : {name}")
    start = time.perf_counter()
    value = _evaluate(name, state, params) if isinstance(state, AppState) and state.recent \
        else None
    status = "unknown" if value is None else "pass" if value else "fail"
    revision = getattr(state, "revision", -1)
    return CheckResult(status, DETAILS[status], revision, (time.perf_counter() - start) * 1000)


def progress_signature(name: str, state: Any, params: dict) -> str:
    if not isinstance(state, AppState):
        return "null"
    if name == "window_title":
        data: Any = state.window_title
    elif name == "visual_assert":
        verdict = state.verdicts.get(assertion_key(params))
        data = None if verdict is None else verdict.answer
    else:
        found = lookup(state, params["target"])
        data = None if found is None else [
            (n.get("role"), n.get("name"), n.get("value"), sorted(n.get("states", ())))
            for n in found.nodes
        ]
    return json.dumps(data, sort_keys=True, default=str)
