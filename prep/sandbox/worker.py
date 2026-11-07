"""Point d'entrée exécuté exclusivement dans Blender."""

import ast
import inspect
import json
import sys
import textwrap
import time
from pathlib import Path

import bpy

PRIMITIVES = (
    "cube",
    "uv_sphere",
    "ico_sphere",
    "cylinder",
    "cone",
    "torus",
    "plane",
    "monkey",
    "circle",
    "grid",
)
CACHE = None


def operator(identifier):
    module, name = identifier.split(".")
    return getattr(getattr(bpy.ops, module), name)


def topology(obj):
    if obj.type != "MESH":
        return None
    return [len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)]


def state():
    return [
        {"name": obj.name, "type": obj.type, "topology": topology(obj)}
        for obj in bpy.context.scene.objects
    ]


def fingerprints():
    cache = CACHE / (".".join(map(str, bpy.app.version)) + "-fingerprints.json")
    if cache.exists():
        return json.loads(cache.read_text())
    scene = bpy.data.scenes.new("Reference")
    result = {}
    try:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            for name in PRIMITIVES:
                operator(f"mesh.primitive_{name}_add")()
                obj = bpy.context.view_layer.objects.active
                result[name] = topology(obj)
                bpy.data.objects.remove(obj, do_unlink=True)
    finally:
        bpy.data.scenes.remove(scene)
    cache.write_text(json.dumps(result))
    return result


def evaluate(check, before, after, table):
    if check.get("name") != "object_exists":
        return "unknown"
    params = check.get("params", {})
    expected = table.get(params.get("primitive"))
    if expected is None:
        return "unknown"
    old = {obj["name"] for obj in before}
    new = [obj for obj in after if obj["name"] not in old]
    matching = [
        obj for obj in new if obj["type"] == params.get("type") and obj["topology"] == expected
    ]
    aliases = [name for name, value in table.items() if value == expected]
    if matching and len(aliases) == 1 and len(matching) == 1:
        return "pass"
    return "unknown" if matching else "fail"


def dump_map():
    import bl_ui

    menus, ids = {}, {f"mesh.primitive_{name}_add" for name in PRIMITIVES}
    for module in vars(bl_ui).values():
        if not inspect.ismodule(module):
            continue
        for cls in vars(module).values():
            if not inspect.isclass(cls) or not issubclass(cls, bpy.types.Menu):
                continue
            if not hasattr(cls, "draw"):
                continue
            entries = []
            try:
                tree = ast.parse(textwrap.dedent(inspect.getsource(cls.draw)))
            except (OSError, TypeError, IndentationError):
                continue
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"operator", "menu"}
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    continue
                identifier = node.args[0].value
                label = next(
                    (
                        kw.value.value
                        for kw in node.keywords
                        if kw.arg == "text" and isinstance(kw.value, ast.Constant)
                    ),
                    "",
                )
                entries.append({"kind": node.func.attr, "id": identifier, "label": label})
                if node.func.attr == "operator":
                    ids.add(identifier)
            menus[cls.__name__] = {
                "label": getattr(cls, "bl_label", cls.__name__),
                "call_menu": {"operator": "wm.call_menu", "name": cls.__name__},
                "entries": entries,
            }
    operators = {}
    for identifier in sorted(ids):
        if identifier.count(".") != 1:
            continue
        try:
            rna = operator(identifier).get_rna_type()
            properties = []
            for prop in rna.properties:
                if prop.identifier == "rna_type":
                    continue
                default = (
                    getattr(prop, "default_array", None)
                    if getattr(prop, "is_array", False)
                    else getattr(prop, "default", None)
                )
                if default is not None and not isinstance(default, (str, int, float, bool)):
                    default = list(default)
                properties.append(
                    {"identifier": prop.identifier, "type": prop.type, "default": default}
                )
            operators[identifier] = {
                "name": rna.name,
                "description": rna.description,
                "properties": properties,
            }
        except (AttributeError, RuntimeError, KeyError):
            continue
    return {
        "blender_version": bpy.app.version_string.split()[0],
        "menus": menus,
        "operators": operators,
        "primitive_fingerprints": fingerprints(),
    }


def main(args):
    global CACHE
    CACHE = Path(args["fingerprint_cache"])
    started = time.perf_counter()
    version = ".".join(map(str, bpy.app.version))
    operation = args["operation"]
    if operation == "version":
        return {"blender_version": version}
    if operation == "ui_map":
        result = dump_map()
    elif operation == "reset":
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for collection in list(bpy.data.collections):
            bpy.data.collections.remove(collection)
        bpy.ops.wm.save_as_mainfile(filepath=args["checkpoint_out"])
        result = {"after": state()}
    else:
        bpy.ops.wm.open_mainfile(filepath=args["checkpoint_in"])
        before = state()
        if operation == "inspect":
            return {
                "before": before,
                "after": before,
                "blender_version": version,
                "check_result": evaluate(args["check"], before, before, fingerprints()),
            }
        procedure = args["procedures"][args["procedure"]]
        if bpy.context.mode != procedure["preconditions"]["mode"]:
            raise ValueError("Mode incompatible")
        table = fingerprints()
        operator(procedure["operator_id"])()
        after = state()
        result = {
            "before": before,
            "after": after,
            "check_result": evaluate(args["check"], before, after, table),
            "primitive_fingerprints": table,
        }
        bpy.ops.wm.save_as_mainfile(filepath=args["checkpoint_out"])
    result.update(blender_version=version, duration=time.perf_counter() - started)
    return result


if __name__ == "__main__":
    source, destination = sys.argv[sys.argv.index("--") + 1 :]
    Path(destination).write_text(json.dumps(main(json.loads(Path(source).read_text()))))
