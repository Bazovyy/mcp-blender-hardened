from __future__ import annotations
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"addon"))
try: import bpy
except ImportError:
 import pytest;pytest.skip("Blender-only subprocess test",allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers
from blender_mcp_addon.file_policy import FilePolicyError

bpy.ops.wm.read_factory_settings(use_empty=True);h=CommandHandlers();scene=bpy.context.scene
bpy.ops.mesh.primitive_cube_add();bpy.ops.object.camera_add(location=(4,-4,3));cam=bpy.context.object;scene.camera=cam;direction=bpy.data.objects['Cube'].location-cam.location;cam.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=64;scene.render.resolution_y=64;scene.render.resolution_percentage=100
scene.render.filepath='ORIGINAL_PATH';scene.render.image_settings.file_format='JPEG';scene.frame_start=3;scene.frame_end=9
p=Path(tempfile.gettempdir())/f'mcp_file_policy_{os.getpid()}.png';p.write_bytes(b'keep')
try:
 try:h.handle('render_image',{'output_path':str(p),'file_format':'PNG'})
 except FilePolicyError as e: assert e.code=='file_exists'
 else: raise AssertionError('existing output was overwritten without opt-in')
 assert p.read_bytes()==b'keep';assert scene.render.filepath=='ORIGINAL_PATH';assert scene.render.image_settings.file_format=='JPEG';assert scene.frame_start==3 and scene.frame_end==9
 r=h.handle('render_image',{'output_path':str(p),'file_format':'PNG','overwrite':True});assert Path(r['output_path'])==p.resolve();assert p.stat().st_size>8
 assert scene.render.filepath=='ORIGINAL_PATH';assert scene.render.image_settings.file_format=='JPEG'
 print('TASK12_FILE_POLICY_PASS')
finally:
 try:p.unlink(missing_ok=True)
 except Exception:pass
