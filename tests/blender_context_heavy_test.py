from __future__ import annotations
import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"addon"))
try:
 import bpy,bmesh
except ImportError:
 import pytest; pytest.skip("Blender-only subprocess test",allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers
from blender_mcp_addon.context import find_view3d_context

def reset(): bpy.ops.wm.read_factory_settings(use_empty=True); return CommandHandlers()
def ico(name='Sculpt'):
 bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2);o=bpy.context.object;o.name=name;return o

def mesh_filter():
 h=reset();o=ico();before=[tuple(v.co) for v in o.data.vertices];r=h.handle('sculpt_mesh_filter',{'object_name':o.name,'filter_type':'SMOOTH','strength':0.25,'iterations':1});assert r['success'],r;after=[tuple(v.co) for v in o.data.vertices];assert before!=after

def mask_modes():
 h=reset();o=ico();r=h.handle('sculpt_mask_by_topology',{'object_name':o.name,'mask_type':'ALL'});assert r['success'],r;a=o.data.attributes.get('.sculpt_mask');assert a and all(x.value>0.99 for x in a.data)
 r=h.handle('sculpt_mask_by_topology',{'object_name':o.name,'mask_type':'RANDOM','invert':True,'blur_iterations':1});assert r['success'],r;vals=[x.value for x in o.data.attributes['.sculpt_mask'].data];assert min(vals)>=0 and max(vals)<=1 and max(vals)-min(vals)>0.01

def extract_mask():
 h=reset();o=ico();a=o.data.attributes.new('.sculpt_mask','FLOAT','POINT');
 for i,x in enumerate(a.data): x.value=1.0 if i%2==0 else 0.0
 r=h.handle('sculpt_extract_mask',{'object_name':o.name,'thickness':0.02,'smooth_iterations':1});assert r['success'],r;new=bpy.data.objects[r['extracted_object']];assert len(new.data.polygons)>0

def face_set_linked():
 h=reset();bpy.ops.mesh.primitive_cube_add(location=(-2,0,0));a=bpy.context.object;a.name='PartA';bpy.ops.mesh.primitive_cube_add(location=(2,0,0));b=bpy.context.object;b.name='PartB';a.select_set(True);b.select_set(True);bpy.context.view_layer.objects.active=a;bpy.ops.object.join();a.name='TwoShells'
 r=h.handle('sculpt_face_set_create',{'object_name':'TwoShells','criteria':'LINKED'});assert r['success'] and r['face_set_count']==2,r

def voxel_remesh():
 h=reset();o=ico();r=h.handle('sculpt_remesh_voxel',{'object_name':o.name,'voxel_size':0.3});assert r['success'],r;assert r['vertices_after']>0

def physics_small():
 h=reset();bpy.ops.mesh.primitive_cube_add(location=(0,0,1));o=bpy.context.object;o.name='RB';r=h.handle('physics_rigid_body_add',{'object_name':'RB'});assert r['success'],r
 r=h.handle('physics_simulate',{'frame_start':1,'frame_end':2,'apply_results':False});assert r['success'],r;assert r.get('blocking_risk')=='synchronous_cache_bake',r

def context_gate():
 h=reset();o=ico();assert find_view3d_context() is None
 r=h.handle('sculpt_mesh_filter',{'object_name':o.name,'filter_type':'SHARPEN'});assert not r['success'] and r.get('code')=='context_required',r
 r=h.handle('sculpt_mask_by_topology',{'object_name':o.name,'mask_type':'CAVITY'});assert not r['success'] and r.get('code')=='context_required',r

CASES={'mesh_filter':mesh_filter,'mask_modes':mask_modes,'extract_mask':extract_mask,'face_set_linked':face_set_linked,'voxel_remesh':voxel_remesh,'physics_small':physics_small,'context_gate':context_gate}
if __name__=='__main__':
 a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];case=a[0] if a else ''
 if case not in CASES: raise SystemExit(f'unknown case {case}')
 CASES[case]();print(f'CONTEXT52_PASS:{case}')