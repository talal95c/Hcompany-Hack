"""Checks locaux : aucune identité déduite du nom d'un objet."""

from collections import Counter
from math import hypot
from typing import Any

import bpy


def topology(obj: Any, primitive: str, provenance: dict) -> bool:
    mesh = obj.data
    if not mesh.vertices or not mesh.polygons:
        return False
    if any(len(p.vertices) != 4 for p in mesh.polygons):
        return False
    if primitive == "cube":
        return len(mesh.vertices) == 8 and len(mesh.polygons) == 6
    adjacency = {v.index: set() for v in mesh.vertices}
    for edge in mesh.edges:
        a, b = edge.vertices
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen, pending = set(), [0]
    while pending:
        vertex = pending.pop()
        if vertex not in seen:
            seen.add(vertex)
            pending.extend(adjacency[vertex] - seen)
    return (
        all(len(neighbors) == 4 for neighbors in adjacency.values())
        and len(seen) == len(mesh.vertices)
        and len(mesh.vertices) - len(mesh.edges) + len(mesh.polygons) == 0
        and len(mesh.vertices) == provenance["major_segments"] * provenance["minor_segments"]
    )


class Evaluator:
    def __init__(self) -> None:
        self.provenance: dict[int, dict] = {}

    def record(self, obj: Any, primitive: str, properties: dict) -> None:
        self.provenance[obj.as_pointer()] = {"primitive": primitive, **properties}

    def matching(self, primitive: str) -> list:
        return [
            obj
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
            and (p := self.provenance.get(obj.as_pointer()))
            and p["primitive"] == primitive
            and topology(obj, primitive, p)
        ]

    def derived(self, params: dict | None = None) -> list:
        params = params or {"fraction_min": 0.3, "fraction_max": 0.7, "epsilon": 1e-5}
        subjects = self.matching("torus")
        if len(subjects) != 1:
            return []
        torus = subjects[0]
        points = [torus.matrix_world @ v.co for v in torus.data.vertices]
        result = []
        for obj in bpy.context.scene.objects:
            if obj == torus or obj.type != "MESH" or not obj.data.polygons:
                continue
            fraction = len(obj.data.polygons) / len(torus.data.polygons)
            edges = Counter(
                tuple(sorted(edge)) for face in obj.data.polygons for edge in face.edge_keys
            )
            if (
                params["fraction_min"] <= fraction <= params["fraction_max"]
                and any(count == 1 for count in edges.values())
                and all(
                    min((obj.matrix_world @ v.co - point).length for point in points)
                    <= params["epsilon"]
                    for v in obj.data.vertices
                )
            ):
                result.append(obj)
        return result

    def resolve(self, role: str) -> Any | None:
        candidates = self.derived() if role == "icing" else self.matching(role)
        return candidates[0] if len(candidates) == 1 else None

    def evaluate(self, check: dict) -> str:
        name, params = check["name"], check["params"]
        if name == "object_exists":
            meshes = [obj for obj in bpy.context.scene.objects if obj.type == params["type"]]
            if not meshes:
                return "fail"
            if self.matching(params["primitive"]):
                return "pass"
            return "unknown"
        if name == "derived_part":
            return "pass" if self.derived(params) else "fail"
        if name == "torus_extra_faces":
            candidates = [
                obj
                for obj in bpy.context.scene.objects
                if obj.type == "MESH"
                and (p := self.provenance.get(obj.as_pointer()))
                and p["primitive"] == "torus"
            ]
            if len(candidates) != 1:
                return "unknown"
            obj = candidates[0]
            provenance = self.provenance[obj.as_pointer()]
            return (
                "pass"
                if len(obj.data.polygons)
                > (provenance["major_segments"] * provenance["minor_segments"])
                else "fail"
            )
        obj = self.resolve(params.get("target", "torus"))
        if obj is None:
            return "fail"
        if name == "torus_dimensions":
            radii = [hypot(v.co.x, v.co.y) for v in obj.data.vertices]
            major = (max(radii) + min(radii)) / 2
            minor = (max(radii) - min(radii)) / 2
            provenance = self.provenance[obj.as_pointer()]
            ok = (
                abs(major - params["major_radius"]) <= params["tolerance"]
                and abs(minor - params["minor_radius"]) <= params["tolerance"]
                and provenance["major_segments"] == params["major_segments"]
                and provenance["minor_segments"] == params["minor_segments"]
                and len({round(v.co.z, 5) for v in obj.data.vertices})
                == params["minor_segments"] // 2 + 1
            )
        elif name == "modifier":
            ok = any(
                mod.type == params["type"]
                and ("levels" not in params or mod.levels == params["levels"])
                and (
                    "thickness_min" not in params
                    or params["thickness_min"] <= mod.thickness <= params["thickness_max"]
                )
                for mod in obj.modifiers
            )
        elif name == "shade_smooth":
            ok = bool(obj.data.polygons) and all(p.use_smooth for p in obj.data.polygons)
        elif name == "flat_faces":
            ok = any(not p.use_smooth for p in obj.data.polygons)
        elif name in {"mesh_deformed", "vertex_spike"}:
            deviations = [
                abs(
                    hypot(hypot(v.co.x, v.co.y) - params["major_radius"], v.co.z)
                    - params["minor_radius"]
                )
                for v in obj.data.vertices
            ]
            affected = sum(deviation > params["threshold"] for deviation in deviations)
            ok = (affected >= 2 if name == "mesh_deformed" else affected == 1) and topology(
                obj, "torus", self.provenance[obj.as_pointer()]
            )
        elif name == "material_color":
            materials = [slot.material for slot in obj.material_slots]
            colors = {
                i
                for i, mat in enumerate(materials)
                if mat
                and mat.use_nodes
                and any(
                    node.type == "BSDF_PRINCIPLED"
                    and all(
                        abs(a - b) <= params["tolerance"]
                        for a, b in zip(
                            node.inputs["Base Color"].default_value, params["rgba"], strict=True
                        )
                    )
                    for node in mat.node_tree.nodes
                )
            }
            ok = bool(obj.data.polygons) and all(
                p.material_index in colors for p in obj.data.polygons
            )
        else:
            raise ValueError(f"Check non autorisé : {name}")
        return "pass" if ok else "fail"
