import bpy
import os
from pathlib import Path

bpy.context.preferences.view.show_splash = False
bpy.context.preferences.view.show_tooltips = False
cube = bpy.data.objects.get('Cube')
for area in bpy.context.screen.areas:
    if area.type == 'PROPERTIES':
        area.spaces.active.context = 'OBJECT'
    if area.type == 'VIEW_3D':
        area.spaces.active.region_3d.view_distance = 7
        area.spaces.active.shading.type = 'MATERIAL'
        area.spaces.active.shading.studiolight_background_alpha = 0
        area.spaces.active.overlay.show_floor = False
        area.spaces.active.overlay.show_axis_x = False
        area.spaces.active.overlay.show_axis_y = False

def ready():
    Path(os.environ['RIO_CAPTURE_READY']).touch()

def clear_material():
    cube.data.materials.clear()
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    bpy.app.timers.register(ready, first_interval=6)

bpy.app.timers.register(clear_material, first_interval=25)
