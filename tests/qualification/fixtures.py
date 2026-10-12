from __future__ import annotations
import json,os,shutil,tempfile
from pathlib import Path

def prepare_standard(case_name: str) -> dict:
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root=Path(tempfile.mkdtemp(prefix='mcp_qual_'))
    def cube(name,loc):
        bpy.ops.mesh.primitive_cube_add(location=loc);o=bpy.context.object;o.name=name
        if not o.data.uv_layers:o.data.uv_layers.new(name='UVMap')
        return o
    objs={}
    for name,loc in [('Cube',(0,0,0)),('Target',(0,0,0)),('Tool',(0.5,0,0)),('Source',(3,0,0)),('Ground',(0,0,-2)),('Domain',(6,0,0)),('Flow',(6,0,0)),('HighPoly',(9,0,0)),('LowPoly',(9,0,0)),('Profile',(12,0,0)),('DeleteMe',(15,0,0)),('Cube_LOD0',(18,0,0)),('Cube_LOD1',(21,0,0))]: objs[name]=cube(name,loc)
    mat=bpy.data.materials.new('Mat');mat.use_nodes=True;objs['Cube'].data.materials.append(mat)
    mat2=bpy.data.materials.new('Mat2');mat2.use_nodes=True
    bevel=objs['Cube'].modifiers.new('Bevel','BEVEL');bevel.width=0.05
    text_data=bpy.data.curves.new('TextData','FONT');text_data.body='A';text_obj=bpy.data.objects.new('TextObj',text_data);bpy.context.collection.objects.link(text_obj)
    cv=bpy.data.curves.new('CurveData','CURVE');cv.dimensions='3D';sp=cv.splines.new('POLY');sp.points.add(2)
    for pt,co in zip(sp.points,((0,0,0,1),(1,0,0,1),(2,1,0,1))):pt.co=co
    curve=bpy.data.objects.new('Curve',cv);bpy.context.collection.objects.link(curve)
    col=bpy.data.collections.new('TestCollection');bpy.context.scene.collection.children.link(col)
    bpy.ops.object.camera_add(location=(5,-5,4));cam=bpy.context.object;cam.name='Camera';cam.rotation_euler=((objs['Target'].location-cam.location).to_track_quat('-Z','Y').to_euler());bpy.context.scene.camera=cam
    bpy.ops.object.light_add(type='SUN',location=(0,0,5));bpy.context.object.name='Sun'
    scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=32;scene.render.resolution_y=32;scene.render.resolution_percentage=100;scene.frame_start=1;scene.frame_end=2
    arm_data=bpy.data.armatures.new('RigData');rig=bpy.data.objects.new('Rig',arm_data);bpy.context.collection.objects.link(rig);bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT');bone=arm_data.edit_bones.new('Bone');bone.head=(0,0,0);bone.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
    # A deterministic stored pose for pose_library_apply.
    pb=rig.pose.bones['Bone'];pose={'Bone':{'location':list(pb.location),'rotation_quaternion':list(pb.rotation_quaternion),'rotation_euler':list(pb.rotation_euler),'rotation_mode':pb.rotation_mode,'scale':list(pb.scale)}}
    rig['_pose_lib_QualPose']=json.dumps(pose);rig['_pose_lib_index']=json.dumps(['QualPose'])
    objs['Cube'].location.x=0;objs['Cube'].keyframe_insert('location',frame=1);objs['Cube'].location.x=0.2;objs['Cube'].keyframe_insert('location',frame=2);objs['Cube'].location.x=0
    bpy.ops.object.select_all(action='DESELECT');objs['Cube'].select_set(True);bpy.context.view_layer.objects.active=objs['Cube'];bpy.ops.rigidbody.object_add(type='ACTIVE')
    # Multires is case-specific because voxel remesh cannot coexist with it.
    if case_name in {'blender_sculpt_multires_reshape','blender_bake_from_multires'}:
        bpy.ops.object.select_all(action='DESELECT');objs['Target'].select_set(True);bpy.context.view_layer.objects.active=objs['Target']
        multires=objs['Target'].modifiers.new('Multires','MULTIRES');bpy.ops.object.multires_subdivide(modifier=multires.name,mode='CATMULL_CLARK')
    mask=objs['Target'].data.attributes.get('.sculpt_mask') or objs['Target'].data.attributes.new('.sculpt_mask','FLOAT','POINT')
    for i,v in enumerate(mask.data):v.value=1.0 if i%2==0 else 0.0
    ng=bpy.data.node_groups.new('GeoGroup','GeometryNodeTree');ng.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');ng.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry');ni=ng.nodes.new('NodeGroupInput');no=ng.nodes.new('NodeGroupOutput');ng.links.new(ni.outputs['Geometry'],no.inputs['Geometry'])
    gn=objs['Cube'].modifiers.new('GeometryNodes','NODES');gn.node_group=ng
    image_path=root/'input.png';img=bpy.data.images.new('QualImage',width=16,height=16,alpha=True);img.generated_color=(0.2,0.4,0.6,1.0);img.filepath_raw=str(image_path);img.file_format='PNG';img.save()
    mask_path=root/'mask.png';img2=bpy.data.images.new('QualMask',width=16,height=16,alpha=True);img2.generated_color=(1,1,1,1);img2.filepath_raw=str(mask_path);img2.file_format='PNG';img2.save()
    from blender_mcp_addon.jobs import JobStep, submit_job
    job_id=submit_job('qualification',lambda j:JobStep(done=False,delay_seconds=60.0))
    if case_name == 'blender_save':bpy.ops.wm.save_as_mainfile(filepath=str(root/'current.blend'))
    # server_restart tests the handler scheduling contract; transport restart is covered separately.
    if case_name == 'blender_server_restart':
        import blender_mcp_addon as addon
        class FakeServer:
            is_running=True
            def __init__(self):self.restart_requested=False
            def request_restart(self):self.restart_requested=True
        addon._server=FakeServer()
    # Build local import fixture before any mode-specific setup.
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.mode!='OBJECT' else None
    obj_path=root/'fixture.obj';bpy.ops.object.select_all(action='DESELECT');objs['Source'].select_set(True);bpy.context.view_layer.objects.active=objs['Source'];bpy.ops.wm.obj_export(filepath=str(obj_path),export_selected_objects=True)
    # Initialize undo only after all fixtures are built: undo invalidates bpy ID references.
    if case_name in {'blender_undo','blender_redo'}:
        cube_obj=bpy.data.objects.get('Cube');bpy.ops.object.select_all(action='DESELECT');cube_obj.select_set(True);bpy.context.view_layer.objects.active=cube_obj
        bpy.ops.ed.undo_push(message='qualification-base');cube_obj.location.x=1.25;bpy.ops.ed.undo_push(message='qualification-mutated')
        if case_name=='blender_redo':bpy.ops.ed.undo()
    if case_name == 'blender_msfs_livery_set_paint_brush':
        bpy.ops.object.select_all(action='DESELECT');objs['Cube'].select_set(True);bpy.context.view_layer.objects.active=objs['Cube'];bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
    return {'root':root,'image':image_path,'mask':mask_path,'import_file':obj_path,'job_id':job_id}

def cleanup_standard(fixture: dict|None) -> None:
    if fixture and fixture.get('root'):shutil.rmtree(fixture['root'],ignore_errors=True)

def resolve_tokens(value, fixture: dict):
    if isinstance(value,str) and value.startswith('$'):
        root=fixture['root'];mapping={'$IMAGE':fixture['image'],'$MASK':fixture['mask'],'$IMPORT_FILE':fixture['import_file'],'$ROOT':root}
        if value == '$JOB':return str(fixture['job_id'])
        if value in mapping:return str(mapping[value])
        if value.startswith('$OUT/'):
            p=root/value[5:];p.parent.mkdir(parents=True,exist_ok=True);return str(p)
    if isinstance(value,list):return [resolve_tokens(v,fixture) for v in value]
    if isinstance(value,dict):return {k:resolve_tokens(v,fixture) for k,v in value.items()}
    return value