"""Original Holo Tutor computer. Run with Blender 4.5 (see landing/README.md)."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument("--center-only", action="store_true")
parser.add_argument("--size", type=int, default=640)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
root = Path(__file__).resolve().parents[1]
output = root / "render-work"
output.mkdir(exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 20
scene.cycles.use_denoising = True
scene.render.resolution_x = args.size
scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.world.color = (0.22, 0.22, 0.22)
scene.view_settings.view_transform = "AgX"


def material(name, color, metallic=0, roughness=0.4):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return mat


ivory = material("warm ceramic", (0.66, 0.56, 0.40), roughness=0.32)
edge = material("bezel", (0.10, 0.09, 0.07), roughness=0.28)
dark = material("vents", (0.07, 0.06, 0.05))
accent = material("violet key", (0.34, 0.22, 0.52), roughness=0.25)
metal = material("brushed metal", (0.3, 0.28, 0.24), metallic=0.75)
light = material("power indicator", (0.55, 0.9, 0.6))
light.node_tree.nodes.get("Principled BSDF").inputs["Emission Color"].default_value = (
    0.3, 0.9, 0.4, 1
)
light.node_tree.nodes.get("Principled BSDF").inputs["Emission Strength"].default_value = 2


def box(name, location, dimensions, mat, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = ob.modifiers.new("soft machined edges", "BEVEL")
        mod.width = bevel
        mod.segments = 6
    ob.modifiers.new("weighted normals", "WEIGHTED_NORMAL")
    ob.data.materials.append(mat)
    return ob


box("case", (0, 0, 1.45), (2.35, 1.6, 2.25), ivory, 0.19)
box("base", (0, 0.02, 0.18), (2.25, 1.5, 0.30), ivory, 0.12)
box("base seam", (0, -0.02, 0.34), (2.19, 1.44, 0.035), edge, 0.015)
box("screen bezel", (0, -0.81, 1.62), (2.08, 0.18, 1.70), edge, 0.15)
box("glass surround", (0, -0.906, 1.64), (1.88, 0.04, 1.48), dark, 0.13)
box("disk drive", (-0.15, -0.813, 0.62), (0.98, 0.025, 0.055), dark, 0.016)
box("disk metal", (-0.44, -0.832, 0.62), (0.18, 0.015, 0.026), metal, 0.004)
box("violet switch", (0.78, -0.82, 0.62), (0.19, 0.075, 0.12), accent, 0.035)
box("status light", (0.98, -0.826, 0.62), (0.025, 0.02, 0.025), light, 0.01)
for index in range(9):
    box(f"side vent {index}", (1.178, 0.08 + index * 0.07, 1.65),
        (0.012, 0.026, 0.72), dark, 0.005)
for x in (-0.88, 0.88):
    box("rubber foot", (x, 0, 0.032), (0.22, 0.9, 0.06), dark, 0.025)

bpy.ops.object.text_add(location=(-0.89, -0.815, 0.54), rotation=(math.pi / 2, 0, 0))
label = bpy.context.object
label.name = "embossed wordmark"
label.data.body = "holo"
label.data.size = 0.15
label.data.extrude = 0.001
label.data.materials.append(edge)

# A slightly convex rounded display, with UVs derived from its physical coordinates.
vertices, faces, uvs = [], [], []
width, height, radius = 1.76, 1.34, 0.12
rows, columns = 32, 40
for row in range(rows + 1):
    z = (row / rows - 0.5) * height
    beyond = max(0, abs(z) - (height / 2 - radius))
    xmax = width / 2 - radius + math.sqrt(max(0, radius ** 2 - beyond ** 2))
    for column in range(columns + 1):
        x = (2 * column / columns - 1) * xmax
        y = -0.942 - 0.055 * (1 - (x / (width / 2)) ** 2) * (
            1 - (z / (height / 2)) ** 2
        )
        vertices.append((x, y, z + 1.64))
        uvs.append((x / width + 0.5, z / height + 0.5))
for row in range(rows):
    for column in range(columns):
        i = row * (columns + 1) + column
        faces.append((i, i + 1, i + columns + 2, i + columns + 1))
mesh = bpy.data.meshes.new("curved tube")
mesh.from_pydata(vertices, [], faces)
mesh.uv_layers.new(name="screen UV")
for poly in mesh.polygons:
    poly.use_smooth = True
    for loop in poly.loop_indices:
        mesh.uv_layers.active.data[loop].uv = uvs[mesh.loops[loop].vertex_index]
display = bpy.data.objects.new("display", mesh)
scene.collection.objects.link(display)
screen = material("phosphor display", (0.01, 0.01, 0.01), roughness=0.23)
nodes = screen.node_tree.nodes
texture = nodes.new("ShaderNodeTexImage")
texture.image = bpy.data.images.load(str(root / "public/computer/screen.webp"))
shader = nodes.get("Principled BSDF")
screen.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
screen.node_tree.links.new(texture.outputs["Color"], shader.inputs["Emission Color"])
shader.inputs["Emission Strength"].default_value = 0.75
shader.inputs["Coat Weight"].default_value = 0.35
display.data.materials.append(screen)


def area(name, position, power, size, color):
    bpy.ops.object.light_add(type="AREA", location=position)
    ob = bpy.context.object
    ob.name = name
    ob.data.energy = power
    ob.data.shape = "DISK"
    ob.data.size = size
    ob.data.color = color
    ob.rotation_euler = (Vector((0, 0, 1.3)) - ob.location).to_track_quat("-Z", "Y").to_euler()


area("large softbox", (-3, -4, 6), 500, 4, (1, 0.86, 0.7))
area("rim light", (3, 2, 4), 650, 3, (0.68, 0.70, 1))
area("front fill", (1, -4, 2), 65, 3, (1, 0.9, 0.8))
bpy.ops.object.camera_add()
camera = bpy.context.object
scene.camera = camera
camera.data.type = "ORTHO"
camera.data.ortho_scale = 3.9
metadata = {"columns": 19, "rows": 3, "size": args.size, "frames": []}
for row in range(3):
    for column in range(19):
        yaw = math.radians((column - 9) * 2.3)
        pitch = math.radians(7 + (row - 1) * 7)
        target = Vector((0, -0.05, 1.32))
        camera.location = target + Vector((
            8 * math.sin(yaw) * math.cos(pitch),
            -8 * math.cos(yaw) * math.cos(pitch),
            8 * math.sin(pitch),
        ))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        corners = []
        for point in [(-0.88, -0.95, 2.31), (0.88, -0.95, 2.31),
                      (0.88, -0.95, 0.97), (-0.88, -0.95, 0.97)]:
            projected = world_to_camera_view(scene, camera, Vector(point))
            corners.append([round(projected.x, 6), round(1 - projected.y, 6)])
        metadata["frames"].append({"row": row, "column": column, "screen": corners})
        if args.center_only and (row != 1 or column != 9):
            continue
        scene.render.filepath = str(output / f"frame-{row}-{column}.png")
        bpy.ops.render.render(write_still=True)
(output / "frames.json").write_text(json.dumps(metadata, separators=(",", ":")))
