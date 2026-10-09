import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon"))
try:
    import bpy
except ImportError:
    import pytest
    pytest.skip("Blender-only subprocess test", allow_module_level=True)
from blender_mcp_addon.state_guard import BlenderStateGuard

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
a=bpy.context.object
a.name="GuardA"
bpy.ops.mesh.primitive_cube_add(location=(3,0,0))
b=bpy.context.object
b.name="GuardB"
bpy.ops.object.camera_add(location=(0,-5,2))
cam=bpy.context.object
cam.name="GuardCamera"
for obj in bpy.context.selected_objects:
    obj.select_set(False)
a.select_set(True)
bpy.context.view_layer.objects.active=a
bpy.context.scene.camera=cam
bpy.context.scene.frame_set(12)
bpy.context.scene.render.filepath="before.png"
bpy.context.scene.render.image_settings.file_format="PNG"
bpy.ops.object.mode_set(mode="EDIT")
try:
    with BlenderStateGuard():
        bpy.ops.object.mode_set(mode="OBJECT")
        a.select_set(False)
        b.select_set(True)
        bpy.context.view_layer.objects.active=b
        bpy.context.scene.frame_set(99)
        bpy.context.scene.camera=None
        bpy.context.scene.render.filepath="after.jpg"
        bpy.context.scene.render.image_settings.file_format="JPEG"
        raise RuntimeError("intentional")
except RuntimeError:
    pass
assert bpy.context.view_layer.objects.active is a
assert a.select_get() and not b.select_get()
assert bpy.context.scene.frame_current == 12
assert bpy.context.scene.camera is cam
assert bpy.context.scene.render.filepath == "before.png"
assert bpy.context.scene.render.image_settings.file_format == "PNG"
assert a.mode == "EDIT", a.mode
print("BLENDER_STATE_GUARD_PASS")