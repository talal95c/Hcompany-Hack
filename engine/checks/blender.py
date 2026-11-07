"""Checks Blender (espace blender.*) sur un état add-on récent ; absence de preuve ≠ réussite."""

import copy
import json
import math
import time
from dataclasses import dataclass, field

from engine.checks.base import CheckResult


@dataclass
class SceneState:
    objects: dict[str, dict] = field(default_factory=dict)
    mode: str | None = None
    active: str | None = None
    selected_ids: list[str] | None = None
    revision: int = -1
    latest_revision: int = -1
    complete: bool = False

    def apply(self, event: dict) -> None:
        revision, kind, payload = event["scene_revision"], event["type"], event["payload"]
        self.latest_revision = max(self.latest_revision, revision)
        if revision < self.revision:
            return
        if kind in {"snapshot", "scene.changed"}:
            ids = [o.get("id") for o in payload["objects"]]
            if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                self.complete = False
                return
        if kind != "snapshot" and revision > self.revision + 1:
            self.complete = False
        if kind == "snapshot":
            self.objects = {o["id"]: copy.deepcopy(o) for o in payload["objects"]}
            self.mode, self.active = payload["mode"], payload["active"]
            self.selected_ids = None
            self.complete = True
        elif kind == "scene.changed":
            if not self.complete or revision > self.revision + 1:
                self.complete = False
            updates = {o["id"]: o for o in payload["objects"]}
            for object_id in payload["changed_ids"]:
                if object_id in updates:
                    self.objects[object_id] = copy.deepcopy(updates[object_id])
                else:
                    self.objects.pop(object_id, None)
        elif kind == "mode.changed":
            self.mode = payload["current"]
        elif kind == "selection.changed":
            self.selected_ids, self.active = payload["selected_ids"], payload["active"]
        else:
            return
        self.revision = revision

    @property
    def recent(self) -> bool:
        return self.complete and self.revision == self.latest_revision

    @property
    def has_content(self) -> bool:
        return bool(self.objects)

    def facts(self) -> dict[str, str | None]:
        mode = self.mode
        if mode and mode.startswith("EDIT_"):
            mode = "EDIT"
        return {"mode": mode}


def primitive_geometry(obj: dict, primitive: str) -> bool | None:
    mesh = obj.get("mesh", {})
    if not isinstance(mesh, dict):
        return None
    vertices, faces, edges = mesh.get("verts"), mesh.get("polys"), mesh.get("edges")
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0
           for n in (vertices, faces, edges)):
        return None
    if primitive == "torus":
        valid = vertices >= 9 and faces == vertices
        expected_edges = 2 * vertices
    elif primitive in {"uv_sphere", "sphere"}:
        valid = vertices >= 6 and vertices < faces <= 2 * (vertices - 2)
        expected_edges = vertices + faces - 2
    elif primitive == "cube":
        valid, expected_edges = (vertices, faces) == (8, 6), 12
    elif primitive == "plane":
        valid, expected_edges = (vertices, faces) == (4, 1), 4
    else:
        return None
    return valid and edges == expected_edges


def matches(obj: dict, params: dict) -> bool | None:
    if "type" in params:
        if "type" not in obj:
            return None
        if obj["type"] != params["type"]:
            return False
    if "primitive" in params:
        if "primitive_provenance" not in obj:
            return None
        if obj["primitive_provenance"] != params["primitive"]:
            return False
        return primitive_geometry(obj, params["primitive"])
    return True


def close(actual, expected, tolerance: float) -> bool:
    if isinstance(expected, (list, tuple)):
        return isinstance(actual, (list, tuple)) and len(actual) == len(expected) and all(
            close(a, b, tolerance) for a, b in zip(actual, expected, strict=True)
        )
    if isinstance(expected, (float, int)) and not isinstance(expected, bool):
        return isinstance(actual, (float, int)) and math.isfinite(actual) and math.isclose(
            actual, expected, abs_tol=tolerance, rel_tol=0
        )
    return actual == expected


NAMES = frozenset({
    "object_exists", "object_count", "modifier_present", "material_color", "shading_smooth",
    "mode_is", "selection", "object_transform",
})


def require_check(name: str) -> None:
    if name not in NAMES:
        raise ValueError(f"Check inconnu : {name}")


def evaluate(name: str, state: SceneState, params: dict) -> CheckResult:
    require_check(name)
    start = time.perf_counter()
    value = _evaluate(name, state, params) if state.recent else None
    status = "unknown" if value is None else "pass" if value else "fail"
    return CheckResult(status, {
        "unknown": "Preuve absente ou état incomplet", "pass": "Vérifié", "fail": "Non vérifié",
    }[status], state.revision, (time.perf_counter() - start) * 1000)


def _evaluate(name: str, state: SceneState, params: dict) -> bool | None:
    if name == "mode_is":
        return None if state.mode is None else state.mode == params["mode"]
    candidates = [matches(o, params) for o in state.objects.values()]
    objects = [o for o, match in zip(state.objects.values(), candidates) if match is True]
    if name == "object_exists":
        return True if objects else None if None in candidates else False
    if name == "object_count":
        return None if None in candidates else len(objects) == params["count"]
    if name == "selection":
        ids = state.selected_ids
        if params.get("active"):
            ids = [state.active] if state.active else []
        if ids is None:
            return None
        results = [matches(state.objects.get(i, {}), params) for i in ids]
        return None if None in results else bool(results) and all(results)
    tolerance = params.get("tolerance", 1e-5)
    if tolerance < 0:
        raise ValueError("Tolérance négative")
    results: list[bool | None] = []
    for obj in objects:
        if name == "modifier_present":
            modifiers = obj.get("modifiers")
            if modifiers is None:
                results.append(None)
                continue
            found = [m for m in modifiers if m.get("type") == params["modifier_type"]]
            values = []
            for modifier in found:
                expected = params.get("params", {})
                values.append(None if any(k not in modifier for k in expected) else all(
                    close(modifier[k], v, tolerance) for k, v in expected.items()
                ))
            results.append(True if True in values else None if None in values else False)
        elif name == "material_color":
            materials = obj.get("materials")
            if materials is None:
                results.append(None)
            else:
                values = [None if "base_color" not in m else close(
                    m["base_color"], params["color"], tolerance
                ) for m in materials]
                results.append(True if True in values else None if None in values else False)
        elif name == "shading_smooth":
            smooth = obj.get("mesh", {}).get("shading_smooth", obj.get("shading_smooth"))
            results.append(None if smooth is None else smooth == params.get("smooth", True))
        elif name == "object_transform":
            expected = {k: params[k] for k in ("location", "scale", "rotation") if k in params}
            results.append(None if not expected or any(k not in obj for k in expected) else all(
                close(obj[k], v, tolerance) for k, v in expected.items()
            ))
    return True if True in results else None if None in results or None in candidates else False


def progress_signature(name: str, state: SceneState, params: dict) -> str:
    """Ignore heartbeat et sélection, sauf pour un check de sélection."""
    if name == "selection":
        data = (state.selected_ids, state.active, [
            (i, matches(state.objects.get(i, {}), params)) for i in state.selected_ids or []
        ])
    elif name == "mode_is":
        data = state.mode
    else:
        fields = {
            "object_exists": ("type", "primitive_provenance", "mesh"),
            "object_count": ("type", "primitive_provenance", "mesh"),
            "modifier_present": ("type", "primitive_provenance", "modifiers"),
            "material_color": ("type", "primitive_provenance", "materials"),
            "shading_smooth": ("type", "primitive_provenance", "mesh", "shading_smooth"),
            "object_transform": ("type", "primitive_provenance", "location", "scale", "rotation"),
        }[name]
        data = [(key, {k: obj[k] for k in fields if k in obj})
                for key, obj in sorted(state.objects.items()) if matches(obj, params) is not False]
    return json.dumps(data, sort_keys=True)