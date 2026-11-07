"""Checks du compagnon prouvé sur les données géométriques du capteur."""

import math
import time
from collections import Counter

from engine.checks import CheckResult, SceneState, close, matches


def subjects(state: SceneState, role: str) -> list[dict]:
    if role != "icing":
        return [o for o in state.objects.values() if matches(
            o, {"type": "MESH", "primitive": role}) is True]
    bases = subjects(state, "torus")
    if len(bases) != 1:
        return []
    base = bases[0]["mesh"]
    result = []
    for obj in state.objects.values():
        mesh = obj.get("mesh", {})
        vertices, faces = mesh.get("world_vertices"), mesh.get("faces")
        points = base.get("world_vertices")
        if not vertices or not faces or not points or obj in bases:
            continue
        fraction = mesh["polys"] / base["polys"]
        edges = Counter(tuple(sorted((face[i], face[(i + 1) % len(face)])))
                        for face in faces for i in range(len(face)))
        if (0.3 <= fraction <= 0.7 and 1 in edges.values()
                and all(any(math.dist(v, p) <= 1e-5 for p in points) for v in vertices)):
            result.append(obj)
    return result


def verify(check: dict, state: SceneState) -> bool | None:
    name, params = check["name"], check["params"]
    objects = subjects(state, params.get("target", "torus"))
    if name == "derived_part":
        return bool(subjects(state, "icing"))
    if len(objects) != 1:
        return False
    obj = objects[0]
    mesh = obj.get("mesh", {})
    if name == "modifier":
        return any(m["type"] == params["type"]
                   and ("levels" not in params or m.get("levels") == params["levels"])
                   and ("thickness_min" not in params or params["thickness_min"]
                        <= m.get("thickness", float("-inf")) <= params["thickness_max"])
                   for m in obj.get("modifiers", []))
    if name in {"shade_smooth", "flat_faces"}:
        value = mesh.get("shading_smooth")
        return None if value is None else value if name == "shade_smooth" else not value
    if name == "material_color":
        return any(close(m.get("base_color"), params["rgba"], params["tolerance"])
                   for m in obj.get("materials", []))
    vertices = mesh.get("vertices")
    if not vertices:
        return None
    if name == "torus_dimensions":
        radii = [math.hypot(v[0], v[1]) for v in vertices]
        return (abs((max(radii) + min(radii)) / 2 - params["major_radius"])
                <= params["tolerance"]
                and abs((max(radii) - min(radii)) / 2 - params["minor_radius"])
                <= params["tolerance"]
                and mesh["verts"] == params["major_segments"] * params["minor_segments"]
                and len({round(v[2], 5) for v in vertices}) == params["minor_segments"] // 2 + 1)
    if name in {"mesh_deformed", "vertex_spike"}:
        affected = sum(abs(math.hypot(math.hypot(v[0], v[1]) - params["major_radius"], v[2])
                           - params["minor_radius"]) > params["threshold"] for v in vertices)
        return affected >= 2 if name == "mesh_deformed" else affected == 1
    raise ValueError(f"Check compagnon non pris en charge : {name}")


def evaluate_verification(checks: list[dict], state: SceneState, base: CheckResult) -> CheckResult:
    if base.status != "pass" or not checks:
        return base
    started = time.perf_counter()
    values = [verify(check, state) for check in checks]
    status = "fail" if False in values else "unknown" if None in values else "pass"
    return CheckResult(status, "Compagnon prouvé", state.revision,
                       base.duration_ms + (time.perf_counter() - started) * 1000)
