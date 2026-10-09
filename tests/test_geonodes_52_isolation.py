from pathlib import Path
import subprocess
import pytest
BLENDER=Path(r"C:\SteamLibrary\steamapps\common\Blender\blender.exe")
SCRIPT=Path(__file__).with_name("blender_geonodes_52_test.py")
CASES=['apply_inspect','scatter_scale','scatter_rotation','array_modes','deform_curve','extrude_profile']
@pytest.mark.parametrize('case',CASES)
def test_geonodes_52_isolated(case):
    proc=subprocess.run([str(BLENDER),'--background','--factory-startup','--python',str(SCRIPT),'--',case],capture_output=True,text=True,timeout=30,check=False)
    output=proc.stdout+proc.stderr
    assert proc.returncode==0,output
    assert f'GN52_CASE_PASS:{case}' in output,output
    assert 'Traceback (most recent call last)' not in output,output