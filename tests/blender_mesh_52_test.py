from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon"))
try:
    import bpy
    import bmesh
except ImportError:
    import pytest
    pytest.skip("Blender-only subprocess test", allow_module_level=True)
from blender_mcp_addon.handlers import CommandHandlers


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return CommandHandlers()


def add_grid(name="Grid"):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=5, y_subdivisions=5, size=4)
    obj=bpy.context.object; obj.name=name
    bm=bmesh.new(); bm.from_mesh(obj.data); bm.edges.ensure_lookup_table()
    seed=None
    for e in bm.edges:
        if len(e.link_faces)==2 and all(len(v.link_edges)==4 for v in e.verts):
            seed=e.index; break
    bm.free()
    assert seed is not None
    return obj, seed


def boolean_float():
    h=reset(); bpy.ops.mesh.primitive_cube_add(); a=bpy.context.object; a.name="A"
    bpy.ops.mesh.primitive_cube_add(location=(0.5,0,0)); b=bpy.context.object; b.name="B"
    r=h.handle("boolean_op", {"target":"A","tool":"B","operation":"DIFFERENCE","solver":"FLOAT","apply":False,"hide_tool":False})
    assert r["solver"]=="FLOAT" and a.modifiers[-1].solver=="FLOAT", r


def edge_loop():
    h=reset(); obj,seed=add_grid()
    r=h.handle("mesh_select_edge_loops", {"object_name":obj.name,"edge_index":seed,"ring":False})
    assert r["success"] and r["count"] >= 2, r


def edge_slide():
    h=reset(); obj,seed=add_grid()
    before=[tuple(v.co) for v in obj.data.vertices]
    r=h.handle("mesh_edge_slide", {"object_name":obj.name,"edge_indices":[seed],"factor":0.15,"even":True})
    after=[tuple(v.co) for v in obj.data.vertices]
    assert r["success"] and before != after, r


def loop_cut():
    h=reset(); bpy.ops.mesh.primitive_cube_add(); obj=bpy.context.object; obj.name="Cube"
    before=(len(obj.data.vertices),len(obj.data.edges),len(obj.data.polygons))
    r=h.handle("mesh_loop_cut", {"object_name":"Cube","edge_index":0,"cuts":1,"smoothness":0.0})
    after=(len(obj.data.vertices),len(obj.data.edges),len(obj.data.polygons))
    assert r["success"] and after[0] > before[0] and after[1] > before[1] and after[2] > before[2], (r,before,after)


def knife_context():
    h=reset(); bpy.ops.mesh.primitive_cube_add(); target=bpy.context.object; target.name="Target"
    bpy.ops.mesh.primitive_plane_add(size=1.0); cutter=bpy.context.object; cutter.name="Cutter"
    before=(len(target.data.vertices),len(target.data.edges),len(target.data.polygons),len(target.modifiers))
    r=h.handle("mesh_knife_project", {"target_object":"Target","cutter_object":"Cutter"})
    after=(len(target.data.vertices),len(target.data.edges),len(target.data.polygons),len(target.modifiers))
    assert r["success"] is False and r.get("code")=="context_required", r
    assert before==after and not cutter.hide_get(), (before,after,r)

CASES={"boolean_float":boolean_float,"edge_loop":edge_loop,"edge_slide":edge_slide,"loop_cut":loop_cut,"knife_context":knife_context}
if __name__ == "__main__":
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    case=args[0] if args else ""
    if case not in CASES: raise SystemExit(f"unknown case: {case}")
    CASES[case]()
    print(f"MESH52_CASE_PASS:{case}")