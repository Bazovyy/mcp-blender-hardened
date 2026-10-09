from __future__ import annotations
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"addon"))
try: import bpy
except ImportError:
 import pytest;pytest.skip("Blender-only subprocess test",allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers
from blender_mcp_addon.file_policy import FilePolicyError

CASES=[('export_gltf','.glb',{'export_format':'GLB'}),('export_fbx','.fbx',{}),('export_obj','.obj',{}),('export_stl','.stl',{}),('export_usd','.usd',{})]
root=Path(tempfile.gettempdir())/f'mcp_export_policy_{os.getpid()}';root.mkdir(exist_ok=True)
try:
 for method,suffix,extra in CASES:
  bpy.ops.wm.read_factory_settings(use_empty=True);h=CommandHandlers();bpy.ops.mesh.primitive_cube_add();p=root/(method+suffix)
  params={'filepath':str(p),**extra};r=h.handle(method,params);assert Path(r['filepath'])==p.resolve();assert p.exists() and p.stat().st_size>0,(method,p)
  try:h.handle(method,params)
  except FilePolicyError as e:assert e.code=='file_exists'
  else:raise AssertionError(f'{method} overwrote without opt-in')
  r=h.handle(method,{**params,'overwrite':True});assert p.exists() and p.stat().st_size>0
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);imp=h.handle('import_file',{'filepath':str(p)});assert imp['count']>0,(method,imp)
 print('TASK12_EXPORT_MATRIX_PASS')
finally:
 import shutil;shutil.rmtree(root,ignore_errors=True)
