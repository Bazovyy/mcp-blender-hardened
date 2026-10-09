from pathlib import Path
import subprocess
import pytest

BLENDER=Path(r"C:\SteamLibrary\steamapps\common\Blender\blender.exe")
SCRIPT=Path(__file__).with_name("blender_mesh_52_test.py")
CASES=["boolean_float","edge_loop","edge_slide","loop_cut","knife_context"]

@pytest.mark.parametrize("case", CASES)
def test_mesh_52_case_isolated(case):
    proc=subprocess.run([str(BLENDER),"--background","--factory-startup","--python",str(SCRIPT),"--",case],capture_output=True,text=True,timeout=30,check=False)
    output=proc.stdout+proc.stderr
    assert proc.returncode==0, output
    assert f"MESH52_CASE_PASS:{case}" in output, output
    assert "Traceback (most recent call last)" not in output, output