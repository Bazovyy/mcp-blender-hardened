from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon"))
try:
    import bpy
except ImportError:
    import pytest
    pytest.skip("Blender-only subprocess test", allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return CommandHandlers()

def cube(name, loc=(0,0,0), scale=(1,1,1)):
    bpy.ops.mesh.primitive_cube_add(location=loc); o=bpy.context.object; o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); return o


def instance_count(parent_name):
    deps=bpy.context.evaluated_depsgraph_get()
    return sum(1 for inst in deps.object_instances if inst.is_instance and inst.parent is not None and inst.parent.name==parent_name)

def evaluated_mesh_counts(name):
    deps=bpy.context.evaluated_depsgraph_get(); obj=bpy.data.objects[name].evaluated_get(deps); mesh=obj.to_mesh()
    try: return (len(mesh.vertices),len(mesh.edges),len(mesh.polygons))
    finally: obj.to_mesh_clear()

def curve(name):
    data=bpy.data.curves.new(name,'CURVE'); data.dimensions='3D'; sp=data.splines.new('POLY'); sp.points.add(2)
    for p,co in zip(sp.points,[(0,0,0,1),(2,0,1,1),(4,1,0,1)]): p.co=co
    o=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(o); return o

def apply_inspect():
    h=reset(); cube('Target')
    c=h.handle('geonode_create_group', {'name':'ProbeGN','inputs':[{'name':'Amount','type':'FLOAT','default':1.25},{'name':'Offset','type':'VECTOR','default':[1,2,3]}]})
    assert c['success']
    a=h.handle('geonode_apply', {'object_name':'Target','node_group':'ProbeGN','inputs':{'Amount':2.5,'Offset':[4,5,6]}})
    assert a['success'] and abs(a['inputs']['Amount']-2.5)<1e-6, a
    assert [round(x,5) for x in a['inputs']['Offset']] == [4,5,6], a
    i=h.handle('geonode_inspect', {'object_name':'Target','modifier_name':a['modifier']})
    assert i['success'] and abs(i['inputs']['Amount']['value']-2.5)<1e-6, i

def scatter_scale():
    h=reset(); bpy.ops.mesh.primitive_plane_add(size=4); t=bpy.context.object; t.name='Surface'; cube('Instance',scale=(.1,.1,.1))
    r=h.handle('geonode_scatter_instances', {'target_object':'Surface','instance_object':'Instance','density':3.0,'scale_min':0.5,'scale_max':1.5,'align_to_normal':False})
    assert r['success'], r
    g=bpy.data.node_groups[r['node_group']]
    n=next(n for n in g.nodes if n.label=='Random Scale')
    assert n.inputs['Min'].default_value==0.5 and n.inputs['Max'].default_value==1.5
    assert instance_count('Surface') > 0

def scatter_rotation():
    h=reset(); bpy.ops.mesh.primitive_plane_add(size=4); t=bpy.context.object; t.name='Surface'; cube('Instance',scale=(.1,.1,.1))
    r=h.handle('geonode_scatter_instances', {'target_object':'Surface','instance_object':'Instance','density':3.0,'rotation_random':[10,20,30],'align_to_normal':True})
    assert r['success'], r
    g=bpy.data.node_groups[r['node_group']]
    rot=next(n for n in g.nodes if n.label=='Add Random Rot')
    assert rot.rotation_type=='EULER'
    rr=next(n for n in g.nodes if n.label=='Random Rot')
    assert tuple(round(v,5) for v in rr.inputs['Min'].default_value)==tuple(round(-__import__('math').radians(v),5) for v in [10,20,30])
    assert instance_count('Surface') > 0

def array_modes():
    h=reset(); cube('Instance',scale=(.1,.1,.1))
    for index,mode in enumerate(('LINEAR','GRID_2D','RADIAL','HEXAGONAL')):
        host=f'Host_{mode}'; cube(host,loc=(index*10,0,0))
        r=h.handle('geonode_array_grid', {'object_name':host,'instance_object':'Instance','grid_type':mode,'count_x':3,'count_y':3,'radial_count':6})
        assert r['success'], (mode,r)
        g=bpy.data.node_groups[r['node_group']]
        assert len(g.nodes)>=3
        assert instance_count(host) > 0, mode

def deform_curve():
    h=reset(); cube('Mesh',scale=(2,.2,.2)); curve('Path')
    r=h.handle('geonode_deform_curve', {'object_name':'Mesh','curve_name':'Path','stretch':True})
    assert r['success'], r
    assert bpy.data.objects['Mesh'].modifiers[r['modifier']].node_group is not None
    assert evaluated_mesh_counts('Mesh')[0] > 0

def extrude_profile():
    h=reset(); curve('Path'); bpy.ops.mesh.primitive_circle_add(vertices=8,radius=.2); p=bpy.context.object; p.name='Profile'
    r=h.handle('geonode_extrude_profile', {'profile_object':'Profile','curve_name':'Path','name':'Extruded','fill_caps':True})
    assert r['success'], r
    assert bpy.data.objects[r['object']].modifiers[r['modifier']].node_group is not None
    assert evaluated_mesh_counts(r['object'])[0] > 0

CASES={'apply_inspect':apply_inspect,'scatter_scale':scatter_scale,'scatter_rotation':scatter_rotation,'array_modes':array_modes,'deform_curve':deform_curve,'extrude_profile':extrude_profile}
if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    case=args[0] if args else ''
    if case not in CASES: raise SystemExit(f'unknown case: {case}')
    CASES[case](); print(f'GN52_CASE_PASS:{case}')