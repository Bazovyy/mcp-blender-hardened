from __future__ import annotations
import importlib.util
import math
from pathlib import Path
import sys
import pytest

PKG = Path(__file__).resolve().parents[1] / "addon" / "blender_mcp_addon"

def load(name):
    spec=importlib.util.spec_from_file_location(f"hardening_{name}", PKG / f"{name}.py")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod


def test_numeric_validation_rejects_bool_nan_and_inf():
    v=load("validation")
    with pytest.raises(v.ValidationError): v.require_param({"n": True}, "n", int)
    for bad in ([True,0,1], [math.nan,0,1], [math.inf,0,1]):
        with pytest.raises(v.ValidationError): v.validate_vector3(bad, "vec")
    for bad in ([math.nan,0,0,1], [math.inf,0,0,1]):
        with pytest.raises(v.ValidationError): v.validate_color(bad, "color")


def test_conditional_validation_requires_one_present_value():
    v=load("validation")
    with pytest.raises(v.ValidationError): v.require_any_param({}, ["prompt", "image_path"])
    with pytest.raises(v.ValidationError): v.require_any_param({"prompt": ""}, ["prompt", "image_path"])
    assert v.require_any_param({"image_path": "x.png"}, ["prompt", "image_path"]) == "image_path"


def test_result_envelope_helpers_are_deterministic():
    r=load("result")
    assert r.ok({"x":1}) == {"ok": True, "result": {"x":1}}
    assert r.fail("bad_input", "nope") == {"ok": False, "error": {"code":"bad_input", "message":"nope", "details": {}}}
    assert r.normalize_handler_result({"success": False, "error": "boom"})["ok"] is False