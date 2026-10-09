from __future__ import annotations
import math,os,sys
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"addon"))
try: import bpy
except ImportError:
 import pytest;pytest.skip("Blender-only subprocess test",allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers
from blender_mcp_addon.validation import ValidationError
from blender_mcp_addon.msfs.animation import get_animation_info
from blender_mcp_addon.msfs.livery.painting import setup_paint_mode,set_paint_brush

bpy.ops.wm.read_factory_settings(use_empty=True);h=CommandHandlers()
r=h.handle('object_create',{'type':'cube','name':'Deg','rotation':[0,0,90],'rotation_unit':'DEGREES'});o=bpy.data.objects['Deg'];assert abs(o.rotation_euler.z-math.pi/2)<1e-6
h.handle('object_transform',{'name':'Deg','rotation':[0,0,1.0],'rotation_unit':'RADIANS'});assert abs(o.rotation_euler.z-1.0)<1e-6
try:h.handle('object_transform',{'name':'Deg','rotation':[0,0,1]})
except ValidationError:pass
else:raise AssertionError('rotation without rotation_unit accepted')
o.location.x=0;o.keyframe_insert('location',frame=1);o.location.x=2;o.keyframe_insert('location',frame=10);info=get_animation_info('Deg');assert info['fcurve_count']==3,info;assert 'location' in info['animated_properties'],info
setup=setup_paint_mode('Deg',texture_resolution=(64,64),create_uvs=True);assert 'error' not in setup,setup
brush=bpy.context.tool_settings.image_paint.brush;assert brush is not None
paint=set_paint_brush(preset='soft_airbrush');assert 'error' not in paint,paint;assert brush.curve_distance_falloff_preset=='SMOOTH',brush.curve_distance_falloff_preset
print('TASK13_BLENDER52_PASS')