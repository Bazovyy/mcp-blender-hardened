from pathlib import Path
import subprocess,pytest
BLENDER=Path(r"C:\SteamLibrary\steamapps\common\Blender\blender.exe");SCRIPT=Path(__file__).with_name("blender_context_heavy_test.py")
CASES=['mesh_filter','mask_modes','extract_mask','face_set_linked','voxel_remesh','physics_small','context_gate']
@pytest.mark.parametrize('case',CASES)
def test_context_heavy_case_isolated(case):
 p=subprocess.run([str(BLENDER),'--background','--factory-startup','--python',str(SCRIPT),'--',case],capture_output=True,text=True,timeout=45,check=False);out=p.stdout+p.stderr
 assert p.returncode==0,out;assert f'CONTEXT52_PASS:{case}' in out,out;assert 'Traceback (most recent call last)' not in out,out