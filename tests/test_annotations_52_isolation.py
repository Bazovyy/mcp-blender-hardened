from pathlib import Path
import subprocess,pytest
BLENDER=Path(r"C:\SteamLibrary\steamapps\common\Blender\blender.exe");SCRIPT=Path(__file__).with_name("blender_annotations_52_test.py")
CASES=['annotation','gp_create','markup','engine','control_render','render_state']
@pytest.mark.parametrize('case',CASES)
def test_annotations_render_52_isolated(case):
 p=subprocess.run([str(BLENDER),'--background','--factory-startup','--python',str(SCRIPT),'--',case],capture_output=True,text=True,timeout=45,check=False);o=p.stdout+p.stderr
 assert p.returncode==0,o; assert f'ANNOT_RENDER52_PASS:{case}' in o,o; assert 'Traceback (most recent call last)' not in o,o