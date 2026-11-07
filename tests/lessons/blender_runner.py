"""Exécution bornée des seules actions déclarées dans les compagnons."""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluator import Evaluator  # noqa: E402

ALLOWED = {
    "MESH_OT_primitive_torus_add",
    "MESH_OT_primitive_cube_add",
    "OBJECT_OT_mode_set",
    "OBJECT_OT_subdivision_set",
    "OBJECT_OT_shade_smooth",
    "OBJECT_OT_modifier_add",
    "TRANSFORM_OT_translate",
    "MESH_OT_duplicate",
    "MESH_OT_separate",
}


def write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def activate(obj: Any) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


class Runner:
    def __init__(self) -> None:
        self.evaluator = Evaluator()
        self.last_operator: str | None = None

    def action(self, action: dict) -> None:
        kind = action["kind"]
        if kind in {"operator", "redo"}:
            idname, properties = action["idname"], action["properties"]
            if idname not in ALLOWED:
                raise ValueError(idname)
            if kind == "redo":
                assert self.last_operator == idname
                obj = bpy.context.object
                self.evaluator.provenance.pop(obj.as_pointer())
                bpy.data.objects.remove(obj, do_unlink=True)
            module, operator = idname.split("_OT_")
            result = getattr(getattr(bpy.ops, module.lower()), operator)(**properties)
            assert "FINISHED" in result, (idname, result)
            if idname in {"MESH_OT_primitive_torus_add", "MESH_OT_primitive_cube_add"}:
                primitive = "torus" if "torus" in idname else "cube"
                self.evaluator.record(bpy.context.object, primitive, properties)
            self.last_operator = idname
        elif kind == "property":
            obj = self.evaluator.resolve(action["target"])
            assert obj is not None
            if action["path"] == 'modifiers["Solidify"].thickness':
                modifiers = [mod for mod in obj.modifiers if mod.type == "SOLIDIFY"]
                assert len(modifiers) == 1
                modifiers[0].thickness = action["value"]
            elif action["path"] == "material.base_color":
                material = bpy.data.materials.new("Material")
                material.use_nodes = True
                node = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                node.inputs["Base Color"].default_value = action["value"]
                obj.data.materials.clear()
                obj.data.materials.append(material)
                for face in obj.data.polygons:
                    face.material_index = 0
            else:
                raise ValueError(action["path"])
        elif kind == "select":
            obj = self.evaluator.resolve(action["target"])
            assert obj == bpy.context.object and obj.mode == "EDIT"
            mesh = bmesh.from_edit_mesh(obj.data)
            for face in mesh.faces:
                face.select_set(False)
            for edge in mesh.edges:
                edge.select_set(False)
            for vertex in mesh.verts:
                vertex.select_set(False)
            if "vertex" in action["rule"]:
                bpy.context.tool_settings.mesh_select_mode = (True, False, False)
                max(mesh.verts, key=lambda vertex: vertex.co.x).select_set(True)
            else:
                bpy.context.tool_settings.mesh_select_mode = (False, False, True)
                for face in mesh.faces:
                    if face.calc_center_median().z > action["rule"]["faces_z_above"]:
                        face.select_set(True)
            bmesh.update_edit_mesh(obj.data)
        else:
            raise ValueError(kind)

    def summary(self) -> dict:
        return {
            "mode": bpy.context.mode,
            "objects": [
                {
                    "type": obj.type,
                    "vertices": len(obj.data.vertices),
                    "edges": len(obj.data.edges),
                    "faces": len(obj.data.polygons),
                    "smooth_faces": sum(face.use_smooth for face in obj.data.polygons),
                    "bounds": [
                        [
                            min(v.co[axis] for v in obj.data.vertices),
                            max(v.co[axis] for v in obj.data.vertices),
                        ]
                        for axis in range(3)
                    ]
                    if obj.data.vertices
                    else [],
                    "materials": [
                        [
                            list(node.inputs["Base Color"].default_value)
                            for node in slot.material.node_tree.nodes
                            if node.type == "BSDF_PRINCIPLED"
                        ]
                        for slot in obj.material_slots
                        if slot.material and slot.material.use_nodes
                    ],
                    "provenance": self.evaluator.provenance.get(obj.as_pointer()),
                    "modifiers": [
                        {
                            "type": mod.type,
                            **({"levels": mod.levels} if mod.type == "SUBSURF" else {}),
                            **({"thickness": mod.thickness} if mod.type == "SOLIDIFY" else {}),
                        }
                        for mod in obj.modifiers
                    ],
                }
                for obj in bpy.context.scene.objects
                if obj.type == "MESH"
            ],
        }


def negatives() -> dict:
    clear()
    runner = Runner()
    torus = {"name": "object_exists", "params": {"type": "MESH", "primitive": "torus"}}
    cube = {"name": "object_exists", "params": {"type": "MESH", "primitive": "cube"}}
    result = {"empty_scene": runner.evaluator.evaluate(torus)}
    runner.action(
        {"kind": "operator", "idname": "MESH_OT_primitive_cube_add", "properties": {"size": 2}}
    )
    result["cube_instead_of_torus"] = runner.evaluator.evaluate(torus)
    result["known_error_cube"] = runner.evaluator.evaluate(cube)
    bpy.context.object.name = "Torus"
    result["renamed_cube"] = runner.evaluator.evaluate(torus)
    runner.evaluator.provenance.clear()
    result["untracked_mesh"] = runner.evaluator.evaluate(cube)
    clear()
    runner = Runner()
    runner.action(
        {
            "kind": "operator",
            "idname": "MESH_OT_primitive_torus_add",
            "properties": {
                "major_segments": 48,
                "minor_segments": 12,
                "major_radius": 1,
                "minor_radius": 0.45,
            },
        }
    )
    runner.action(
        {"kind": "operator", "idname": "OBJECT_OT_subdivision_set", "properties": {"level": 1}}
    )
    result["wrong_subdivision"] = runner.evaluator.evaluate(
        {"name": "modifier", "params": {"target": "torus", "type": "SUBSURF", "levels": 2}}
    )
    assert result == {
        "empty_scene": "fail",
        "cube_instead_of_torus": "unknown",
        "known_error_cube": "pass",
        "renamed_cube": "unknown",
        "untracked_mesh": "unknown",
        "wrong_subdivision": "fail",
    }, result
    # La provenance seule ne peut pas prouver une géométrie abîmée.
    obj = bpy.context.object
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    mesh.verts.ensure_lookup_table()
    bmesh.ops.delete(mesh, geom=[mesh.verts[0]], context="VERTS")
    mesh.to_mesh(obj.data)
    mesh.free()
    result["broken_topology"] = runner.evaluator.evaluate(torus)
    assert result["broken_topology"] == "unknown"
    clear()
    return result


def prepare(runner: Runner, step: dict) -> None:
    preconditions = step["preconditions"]
    if preconditions.get("scene") == "empty":
        assert not bpy.context.scene.objects
    if "active" in preconditions:
        obj = runner.evaluator.resolve(preconditions["active"])
        assert obj is not None
        activate(obj)
    if preconditions["mode"] == "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")
    assert bpy.context.object is None or bpy.context.object.mode == preconditions["mode"]


def checkpoint(prefix: list[dict], sidecar: dict, step: dict) -> Runner:
    clear()
    runner = Runner()
    for previous in prefix:
        prepare(runner, previous)
        for action in sidecar[previous["id"]]["expected_actions"]:
            runner.action(action)
    prepare(runner, step)
    return runner


def main(directory: Path, output: Path) -> None:
    start = time.perf_counter()
    assert bpy.app.version == (4, 5, 9), bpy.app.version
    lesson = json.loads((directory / "lesson.json").read_text())
    sidecar = json.loads((directory / "steps.json").read_text())
    clear()
    runner = Runner()
    proof_dir = directory / "proof"
    proof_dir.mkdir(exist_ok=True)
    results = []
    for index, step in enumerate(lesson["steps"]):
        clock = time.perf_counter()
        extra = sidecar[step["id"]]
        checks = [step["check"], *extra["checks"]]
        error_specs = [*step["known_errors"], *extra["known_errors_extra"]]
        error_proofs = []
        for error in error_specs:
            probe = checkpoint(lesson["steps"][:index], sidecar, step)
            error_before = probe.summary()
            mistake_actions = error.get("mistake_actions")
            if mistake_actions is None:
                assert error["code"] == "cube_instead_of_torus"
                mistake_actions = [
                    {
                        "kind": "operator",
                        "idname": "MESH_OT_primitive_cube_add",
                        "properties": {"size": 2},
                    }
                ]
            for action in mistake_actions:
                probe.action(action)
            mistake_result = probe.evaluator.evaluate(error["check"])
            step_results = [probe.evaluator.evaluate(check) for check in checks]
            assert mistake_result == "pass", (step["id"], error["code"], mistake_result)
            assert not all(result == "pass" for result in step_results), (
                step["id"],
                error["code"],
                step_results,
            )
            error_proofs.append(
                {
                    "code": error["code"],
                    "check": error["check"],
                    "actions": mistake_actions,
                    "before": error_before,
                    "after": probe.summary(),
                    "on_mistake": mistake_result,
                    "step_checks_on_mistake": step_results,
                }
            )
        runner = checkpoint(lesson["steps"][:index], sidecar, step)
        before = runner.summary()
        assert all(error["before"] == before for error in error_proofs)
        before_checks = [runner.evaluator.evaluate(check) for check in checks]
        assert not all(result == "pass" for result in before_checks), step["id"]
        for action in extra["expected_actions"]:
            runner.action(action)
        after_checks = [runner.evaluator.evaluate(check) for check in checks]
        assert all(result == "pass" for result in after_checks), (step["id"], after_checks)
        errors = [runner.evaluator.evaluate(error["check"]) for error in error_specs]
        assert "pass" not in errors, (step["id"], errors)
        for error, correct_result in zip(error_proofs, errors, strict=True):
            error["on_correct_path"] = correct_result
            print(
                f"ERROR {lesson['lesson_id']}/{step['id']} {error['code']} "
                f"{error['on_mistake']} {correct_result}",
                flush=True,
            )
        proof = {
            "step_id": step["id"],
            "blender_version": bpy.app.version_string,
            "ui_path_verified": False,
            "before": before,
            "after": runner.summary(),
            "actions": extra["expected_actions"],
            "checks": checks,
            "before_checks": before_checks,
            "after_checks": after_checks,
            "known_errors": errors,
            "error_proofs": error_proofs,
            "seconds": time.perf_counter() - clock,
        }
        write(proof_dir / f"{step['id']}.json", proof)
        results.append(proof)
        print(f"{lesson['lesson_id']:10} {step['id']:24} {proof['seconds']:.6f} s", flush=True)
    negative_results = negatives()
    files = [
        directory / "lesson.json",
        directory / "steps.json",
        directory / "SOURCE.md",
        *[proof_dir / f"{step['id']}.json" for step in lesson["steps"]],
    ]
    total = time.perf_counter() - start
    manifest = {
        "lesson_id": lesson["lesson_id"],
        "blender_version": bpy.app.version_string,
        "ui_path_verified": False,
        "seconds": total,
        "negative_cases": negative_results,
        "sha256": {
            str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        },
    }
    write(proof_dir / "manifest.json", manifest)
    write(output, {"steps": results, "negative_cases": negative_results, "seconds": total})
    print(f"{lesson['lesson_id']:10} TOTAL (interne)          {total:.6f} s", flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :]
    main(Path(args[0]).resolve(), Path(args[1]).resolve())
