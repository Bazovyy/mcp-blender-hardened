"""Pure tests for state guards and transaction metadata."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path
import pytest

ADDON_PACKAGE = Path(__file__).resolve().parents[1] / "addon" / "blender_mcp_addon"

def _load_module(name):
    path = ADDON_PACKAGE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_bpy():
    a = types.SimpleNamespace(name="A", mode="OBJECT", selected=True)
    b = types.SimpleNamespace(name="B", mode="OBJECT", selected=False)
    for obj in (a, b):
        obj.select_set = lambda value, obj=obj: setattr(obj, "selected", bool(value))
        obj.select_get = lambda obj=obj: obj.selected
    objects = {"A": a, "B": b}
    active_box = types.SimpleNamespace(active=a)
    scene = types.SimpleNamespace(
        frame_current=12,
        camera=a,
        render=types.SimpleNamespace(filepath="before.png", engine="BLENDER_EEVEE", image_settings=types.SimpleNamespace(file_format="PNG")),
        tool_settings=types.SimpleNamespace(use_snap=False, use_transform_data_origin=False, mesh_select_mode=(True, False, False)),
    )
    scene.frame_set = lambda frame: setattr(scene, "frame_current", frame)
    context = types.SimpleNamespace(scene=scene, selected_objects=[a], view_layer=types.SimpleNamespace(objects=active_box), object=a)
    data = types.SimpleNamespace(objects=types.SimpleNamespace(get=objects.get))
    ops = types.SimpleNamespace(object=types.SimpleNamespace(mode_set=lambda mode: setattr(active_box.active, "mode", mode)))
    return types.SimpleNamespace(context=context, data=data, ops=ops), a, b


def test_state_guard_restores_after_exception():
    BlenderStateGuard = _load_module("state_guard").BlenderStateGuard
    bpy, a, b = _fake_bpy()
    with pytest.raises(RuntimeError):
        with BlenderStateGuard(bpy_api=bpy):
            a.selected = False
            b.selected = True
            bpy.context.selected_objects = [b]
            bpy.context.view_layer.objects.active = b
            bpy.context.object = b
            bpy.context.scene.frame_current = 99
            bpy.context.scene.camera = b
            bpy.context.scene.render.filepath = "after.jpg"
            bpy.context.scene.render.image_settings.file_format = "JPEG"
            raise RuntimeError("boom")
    assert bpy.context.view_layer.objects.active is a
    assert a.selected and not b.selected
    assert bpy.context.scene.frame_current == 12
    assert bpy.context.scene.camera is a
    assert bpy.context.scene.render.filepath == "before.png"
    assert bpy.context.scene.render.image_settings.file_format == "PNG"


def test_operation_transaction_records_failure_without_implicit_undo():
    OperationTransaction = _load_module("transactions").OperationTransaction
    tx = OperationTransaction(method="mesh_extrude", risk_class="high")
    with pytest.raises(ValueError):
        with tx:
            raise ValueError("bad")
    assert tx.status == "failed"
    assert tx.error == "bad"
    assert tx.operation_id
    assert tx.checkpoint_strategy == "none"