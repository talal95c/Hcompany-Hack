"""Évaluation des checks génériques sur l'application réelle (accessibilité ou vision).

Résultats : "pass", "fail" ou "unknown". Un arbre incomplet, une cible ambiguë ou un
capteur indisponible donnent "unknown", jamais "pass".
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Protocol

from prep.apps import GENERIC_CHECKS
from prep.ui_map.accessibility import clean_name, find_nodes, requested_cells

DEFAULT_TIMEOUT_MS = 3000


class Observer(Protocol):
    async def snapshot(self, *, cells: list[str] | None = None) -> dict[str, Any]: ...
    async def screenshot(self) -> bytes: ...


class VisualJudge(Protocol):
    async def assert_visual(
        self, image_png: bytes, assertion: str, *, region: dict | None = None
    ) -> dict[str, Any]: ...


def _match(actual: Any, expected: Any, mode: str, tolerance: float | None) -> bool:
    if actual is None:
        return False
    text = clean_name(str(actual))
    if isinstance(expected, bool):
        return text.casefold() in ({"true", "1", "yes"} if expected else {"false", "0", "no"})
    if isinstance(expected, int | float) or tolerance is not None:
        try:
            number = float(text.replace("\u202f", "").replace(" ", "").replace(",", "."))
            return abs(number - float(expected)) <= (tolerance or 0)
        except ValueError:
            return False
    wanted = clean_name(str(expected))
    if mode == "contains":
        return wanted.casefold() in text.casefold()
    if mode == "regex":
        return re.search(wanted, text) is not None
    return text == wanted


def _summary(node: dict[str, Any]) -> dict[str, Any]:
    keys = ("role", "native_role", "name", "path", "states", "bounds")
    return {key: node[key] for key in keys if key in node}


def evaluate_snapshot(check: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verdict instantané d'un check d'accessibilité sur un instantané donné."""
    name, params = check["name"], check.get("params", {})
    complete = bool(snapshot.get("complete")) and not snapshot.get("error")
    if snapshot.get("error"):
        return {"result": "unknown", "reason": snapshot["error"].get("code", "ERROR")}
    if not complete:
        return {"result": "unknown", "reason": "arbre incomplet"}
    if name == "window_title":
        titles = [clean_name(t) for t in snapshot.get("windows", [])]
        mode = params.get("match", "contains")
        ok = any(_match(title, params["value"], mode, None) for title in titles)
        if ok:
            return {"result": "pass", "windows": titles}
        return {"result": "fail" if complete else "unknown", "windows": titles}
    target = params["target"]
    if not target.get("role") and not target.get("name"):
        return {"result": "unknown", "reason": "cible sans rôle ni nom : vision requise"}
    nodes = find_nodes(snapshot, target)
    evidence = {"matches": [_summary(node) for node in nodes[:5]], "match_count": len(nodes)}
    if len(nodes) > 1:
        return {**evidence, "result": "unknown", "reason": "AMBIGUOUS_TARGET"}
    if name == "element_exists":
        present = params.get("present", True)
        if nodes:
            return {**evidence, "result": "pass" if present else "fail"}
        if not complete:
            return {**evidence, "result": "unknown", "reason": "arbre incomplet"}
        return {**evidence, "result": "fail" if present else "pass"}
    if not nodes:
        reason = "cible absente" if complete else "arbre incomplet"
        return {**evidence, "result": "fail" if complete else "unknown", "reason": reason}
    if name == "element_value":
        mode, tolerance = params.get("match", "equals"), params.get("tolerance")
        verdicts = {_match(node.get("value"), params["value"], mode, tolerance) for node in nodes}
        evidence["values"] = [node.get("value") for node in nodes[:5]]
    elif name == "element_state":
        wanted, absent = set(params.get("states", [])), set(params.get("absent_states", []))
        verdicts = {
            wanted <= set(node.get("states", [])) and not absent & set(node.get("states", []))
            for node in nodes
        }
    else:
        return {"result": "unknown", "reason": f"check non géré : {name}"}
    if len(verdicts) > 1:
        return {**evidence, "result": "unknown", "reason": "AMBIGUOUS_TARGET"}
    return {**evidence, "result": "pass" if verdicts.pop() else "fail"}


async def evaluate_check(
    check: dict[str, Any],
    observer: Observer,
    judge: VisualJudge | None,
    *,
    wait_for_pass: bool = True,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    """Check sur un état frais ; attend jusqu'à `timeout_ms` qu'il devienne vrai.

    Seul un check visual_assert autorise la vision. Les checks exacts ne sont jamais
    remplacés par une assertion inventée lorsque l'accessibilité devient indisponible.
    """
    started = time.perf_counter()
    name, params = check.get("name"), check.get("params", {})
    if name not in GENERIC_CHECKS:
        evaluate = getattr(observer, "evaluate_app_check", None)
        if evaluate is not None:
            verdict = await evaluate(check)
            return {**verdict, "duration": time.perf_counter() - started}
        return {"result": "unknown", "reason": f"check non générique : {name}", "duration": 0.0}
    if name == "visual_assert":
        if judge is None:
            return {"result": "unknown", "reason": "juge visuel absent", "duration": 0.0}
        image = await observer.screenshot()
        verdict = await judge.assert_visual(image, params["assertion"], region=params.get("region"))
        confidence = float(verdict.get("confidence", 0))
        answer = verdict.get("answer")
        result = "unknown"
        if confidence >= params.get("min_confidence", 0.8) and answer in {"yes", "no"}:
            result = "pass" if answer == "yes" else "fail"
        return {
            **verdict,
            "result": result,
            "sensor": "vision",
            "duration": time.perf_counter() - started,
        }
    timeout = params.get("timeout_ms", DEFAULT_TIMEOUT_MS) / 1000 if wait_for_pass else 0
    deadline = time.monotonic() + timeout
    cells = requested_cells(params.get("target"))
    while True:
        snapshot = await observer.snapshot(cells=cells)
        verdict = evaluate_snapshot(check, snapshot)
        if verdict["result"] == "pass" or time.monotonic() >= deadline:
            break
        await asyncio.sleep(poll_interval)
    verdict["sensor"] = "accessibility"
    verdict["snapshot_complete"] = bool(snapshot.get("complete"))
    verdict["duration"] = time.perf_counter() - started
    return verdict
