"""Recette headless : états réels des primitives Blender, pas de données simulées."""

import json
import sys
from pathlib import Path

import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
objects = []
for primitive, operator, params in [
    ("torus", bpy.ops.mesh.primitive_torus_add, {"major_segments": 48, "minor_segments": 12}),
    ("uv_sphere", bpy.ops.mesh.primitive_uv_sphere_add, {}),
    ("cube", bpy.ops.mesh.primitive_cube_add, {}),
]:
    operator(**params)
    obj = bpy.context.active_object
    objects.append({"id": primitive, "type": obj.type, "primitive_provenance": primitive,
                    "mesh": {"verts": len(obj.data.vertices), "edges": len(obj.data.edges),
                             "polys": len(obj.data.polygons)}})
Path(sys.argv[-1]).write_text(json.dumps({"version": bpy.app.version_string.split()[0],
                                        "mode": "OBJECT", "active": "torus",
                                        "objects": objects}))
