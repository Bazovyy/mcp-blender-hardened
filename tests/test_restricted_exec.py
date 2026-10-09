from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import types
import pytest

PKG = Path(__file__).resolve().parents[1] / "addon" / "blender_mcp_addon"

def load():
    spec=importlib.util.spec_from_file_location("hardening_restricted_exec", PKG / "restricted_exec.py")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod


def test_restricted_exec_allows_small_computation_and_result():
    m=load()
    out=m.execute_restricted("x = 2 + 3\nprint(x)\nresult = {'value': x}", types.SimpleNamespace())
    assert out["result"] == {"value":5}
    assert out["stdout"] == "5\n"

@pytest.mark.parametrize("script", [
    "import os",
    "open('x.txt', 'w')",
    "__import__('socket')",
    "x = bpy.__class__",
    "bpy.ops.wm.open_mainfile(filepath='x.blend')",
    "bpy.ops.wm.save_as_mainfile(filepath='x.blend')",
    "while True:\n    pass",
])
def test_restricted_exec_rejects_unsafe_ast(script):
    m=load()
    with pytest.raises(m.RestrictedExecError):
        m.execute_restricted(script, types.SimpleNamespace())