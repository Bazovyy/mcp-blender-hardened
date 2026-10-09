from mcp_blender.server import TOOLS

def schema(name):
    for tool in TOOLS:
        if tool.name==name:return tool.input_schema
    raise AssertionError(name)

def test_object_vectors_and_rotation_units_are_explicit():
    for name in ('blender_object_create','blender_object_transform'):
        s=schema(name);p=s['properties']
        for key in ('location','rotation','scale'):
            assert p[key]['minItems']==3 and p[key]['maxItems']==3,(name,key,p[key])
        assert p['rotation_unit']['enum']==['RADIANS','DEGREES']
        assert {'if':{'required':['rotation']},'then':{'required':['rotation_unit']}} in s.get('allOf',[])

def test_ai_generate_model_requires_prompt_or_image_path():
    s=schema('blender_ai_generate_model')
    assert {'required':['prompt']} in s.get('anyOf',[])
    assert {'required':['image_path']} in s.get('anyOf',[])

def test_measure_schema_encodes_mode_requirements_and_exact_types():
    s=schema('blender_measure');p=s['properties']
    for key in ('point_a','point_b'):
        assert p[key]['minItems']==3 and p[key]['maxItems']==3
    assert p['edge_indices']['items']['type']=='integer'
    assert p['vertex_indices']['items']['type']=='integer'
    assert p['vertex_indices']['minItems']==2 and p['vertex_indices']['maxItems']==2
    conditional=s.get('allOf',[])
    assert any(x.get('if',{}).get('properties',{}).get('mode',{}).get('const')=='DISTANCE' and set(x['then']['required'])=={'point_a','point_b'} for x in conditional)
    assert any(x.get('if',{}).get('properties',{}).get('mode',{}).get('const')=='EDGE_LENGTH' and x['then']['required']==['edge_indices'] for x in conditional)
    assert any(x.get('if',{}).get('properties',{}).get('mode',{}).get('const')=='VERTEX_DISTANCE' and x['then']['required']==['vertex_indices'] for x in conditional)

def test_52_schemas_do_not_advertise_removed_values():
    assert 'BLENDER_EEVEE_NEXT' not in schema('blender_render_set_engine')['properties']['engine']['enum']
    for name in ('blender_text_add_relief','blender_mesh_add_relief'):
        assert 'FAST' not in schema(name)['properties']['solver']['enum']
        assert 'FLOAT' in schema(name)['properties']['solver']['enum']