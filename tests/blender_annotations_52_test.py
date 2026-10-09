from __future__ import annotations
import os,sys,tempfile
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"addon"))
try:
 import bpy
except ImportError:
 import pytest; pytest.skip("Blender-only subprocess test",allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers

def reset(): bpy.ops.wm.read_factory_settings(use_empty=True); return CommandHandlers()
def camera(name='Cam'):
 bpy.ops.object.camera_add(location=(0,-6,3)); c=bpy.context.object;c.name=name;bpy.context.scene.camera=c;return c
def cube(name='Cube'):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=name;return o

def annotation_case():
 h=reset(); r=h.handle('annotation_add',{'points':[[0,0,0],[1,0,0],[1,1,0]],'layer_name':'Audit','color':[1,0,0,1],'thickness':4}); assert r['success'],r
 ann=bpy.context.scene.annotation; assert ann is not None
 layer=ann.layers.get('Audit'); assert layer is not None and layer.thickness==4
 frame=next(iter(layer.frames)); assert len(frame.strokes)==1 and len(frame.strokes[0].points)==3
 c=h.handle('annotation_clear',{'layer_name':'Audit'}); assert c['success'] and c['layers_removed']==1,c; assert ann.layers.get('Audit') is None

def gp_create_case():
 h=reset(); r=h.handle('grease_pencil_create',{'name':'AuditGP','color':[0.2,0.4,0.8,1],'strokes':[{'points':[[0,0,0],[1,0,0],[1,1,0]],'thickness':8}]}); assert r['success'],r
 o=bpy.data.objects[r['object']]; assert o.type=='GREASEPENCIL'
 layer=o.data.layers.get('Layer'); assert layer is not None
 frame=next(iter(layer.frames)); assert len(frame.drawing.strokes)==1; st=frame.drawing.strokes[0]; assert len(st.points)==3
 assert tuple(round(v,4) for v in st.points[1].position)==(1.0,0.0,0.0)
 assert len(o.data.materials)==1 and o.data.materials[0].grease_pencil is not None

def markup_case():
 h=reset(); scene=bpy.context.scene; scene.render.image_settings.file_format='PNG'
 src=os.path.join(tempfile.gettempdir(),'mcp_markup_src.png'); out=os.path.join(tempfile.gettempdir(),'mcp_markup_out.png')
 img=bpy.data.images.new('MarkupSrc',width=16,height=16); img.generated_color=(0.1,0.2,0.3,1); img.save_render(src,scene=scene)
 try:
  import PIL
  raise AssertionError('Pillow unexpectedly present in Blender test runtime')
 except ImportError: pass
 r=h.handle('grease_pencil_markup',{'render_path':src,'annotations':[{'type':'rectangle','start':[2,2],'end':[12,12],'color':'red'}],'output_path':out}); assert r['success'],r
 assert r['method']=='compositor_fallback' and os.path.exists(out) and os.path.getsize(out)>100,r

def engine_case():
 h=reset(); r=h.handle('render_set_engine',{'engine':'BLENDER_EEVEE'}); assert r['engine']=='BLENDER_EEVEE',r
 from blender_mcp_addon.validation import ValidationError
 try: h.handle('render_set_engine',{'engine':'BLENDER_EEVEE_NEXT'})
 except ValidationError: pass
 else: raise AssertionError('removed BLENDER_EEVEE_NEXT alias accepted')

def control_render_case():
 h=reset(); cube('Control'); camera(); scene=bpy.context.scene; scene.render.resolution_percentage=100; before=(scene.render.engine,scene.render.filepath,scene.render.resolution_x,scene.render.resolution_y)
 p=h._render_control_image('Control','depth'); assert p and os.path.exists(p) and os.path.getsize(p)>100,p
 after=(scene.render.engine,scene.render.filepath,scene.render.resolution_x,scene.render.resolution_y); assert after==before,(before,after)

def render_state_case():
 h=reset(); cube('Target'); cam=camera('OriginalCam'); scene=bpy.context.scene
 scene.render.engine='BLENDER_EEVEE'; scene.render.filepath='STATE_SENTINEL'; scene.render.image_settings.file_format='JPEG'; scene.render.resolution_x=321; scene.render.resolution_y=123; scene.render.resolution_percentage=77; scene.display.shading.light='MATCAP'; scene.display.shading.color_type='SINGLE'
 def snap(): return (scene.render.engine,scene.render.filepath,scene.render.image_settings.file_format,scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage,scene.camera.name if scene.camera else None,scene.display.shading.light,scene.display.shading.color_type)
 before=snap(); out=tempfile.mkdtemp(prefix='mcp_render_state_'); r=h.handle('render_multi_angle',{'object_name':'Target','angles':['front'],'resolution':[32,32],'output_dir':out}); assert r['success'] and os.path.exists(r['renders']['front']),r; assert snap()==before,(before,snap())
 try: h.handle('render_multi_angle',{'object_name':'Target','angles':['front'],'resolution':[64,'bad'],'output_dir':out})
 except (TypeError,ValueError): pass
 assert snap()==before,(before,snap())
 assert scene.camera is cam

CASES={'annotation':annotation_case,'gp_create':gp_create_case,'markup':markup_case,'engine':engine_case,'control_render':control_render_case,'render_state':render_state_case}
if __name__=='__main__':
 a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];case=a[0] if a else ''
 if case not in CASES: raise SystemExit(f'unknown case {case}')
 CASES[case]();print(f'ANNOT_RENDER52_PASS:{case}')