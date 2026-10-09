from __future__ import annotations
import os,sys,tempfile,uuid
from pathlib import Path
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"addon"))
try:
 import bpy
except ImportError:
 import pytest;pytest.skip("Blender-only subprocess test",allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers
from blender_mcp_addon.temp_assets import get_temp_asset_manager

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add();cube=bpy.context.object
cam_data=bpy.data.cameras.new('Cam');cam=bpy.data.objects.new('Cam',cam_data);bpy.context.collection.objects.link(cam);cam.location=(4,-4,3);cam.rotation_euler=((cube.location-cam.location).to_track_quat('-Z','Y').to_euler());bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=96;scene.render.resolution_y=96;scene.render.resolution_percentage=100
h=CommandHandlers();mgr=get_temp_asset_manager()
r=h.handle('render_screenshot',{});assert r['success'],r;p=Path(r['output_path']);assert r['temporary'] and p.exists() and p.stat().st_size>500 and mgr.is_managed(p),r
explicit=Path(tempfile.gettempdir())/f'explicit_mcp_{uuid.uuid4().hex}.png'
r2=h.handle('render_screenshot',{'output_path':str(explicit)});assert r2['success'] and not r2['temporary'] and explicit.exists() and not mgr.is_managed(explicit),r2
explicit.unlink(missing_ok=True)
print('TASK11_SCREENSHOT_PASS')
