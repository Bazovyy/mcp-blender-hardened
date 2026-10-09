"""Capture and restore volatile Blender UI/scene state around temporary mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import bpy as _bpy
except ImportError:  # Host-side unit tests inject an API explicitly.
    _bpy = None


def _api(bpy_api=None):
    api = bpy_api or _bpy
    if api is None:
        raise RuntimeError("BlenderStateGuard requires Blender or an explicit bpy_api")
    return api


@dataclass(slots=True)
class BlenderStateSnapshot:
    active_object: str | None
    selected_objects: tuple[str, ...]
    mode: str
    frame: int
    camera: str | None
    render_filepath: str
    render_format: str
    render_engine: str | None
    render_resolution_x: int | None
    render_resolution_y: int | None
    render_resolution_percentage: int | None
    render_film_transparent: bool | None
    shading_light: str | None
    shading_color_type: str | None
    compositing_node_group: Any
    use_pass_z: bool | None
    use_pass_normal: bool | None
    use_snap: bool | None
    use_transform_data_origin: bool | None
    mesh_select_mode: tuple[bool, ...] | None

    @classmethod
    def capture(cls, bpy_api=None) -> "BlenderStateSnapshot":
        api = _api(bpy_api)
        context = api.context
        scene = context.scene
        active = context.view_layer.objects.active
        tool = getattr(scene, "tool_settings", None)
        image_settings = scene.render.image_settings
        display = getattr(scene, "display", None)
        shading = getattr(display, "shading", None)
        view_layer = getattr(context, "view_layer", None)
        return cls(
            active_object=getattr(active, "name", None),
            selected_objects=tuple(obj.name for obj in getattr(context, "selected_objects", ())),
            mode=getattr(getattr(context, "object", None), "mode", "OBJECT"),
            frame=int(scene.frame_current),
            camera=getattr(scene.camera, "name", None),
            render_filepath=str(scene.render.filepath),
            render_format=str(image_settings.file_format),
            render_engine=getattr(scene.render, "engine", None),
            render_resolution_x=getattr(scene.render, "resolution_x", None),
            render_resolution_y=getattr(scene.render, "resolution_y", None),
            render_resolution_percentage=getattr(scene.render, "resolution_percentage", None),
            render_film_transparent=getattr(scene.render, "film_transparent", None),
            shading_light=getattr(shading, "light", None),
            shading_color_type=getattr(shading, "color_type", None),
            compositing_node_group=getattr(scene, "compositing_node_group", None),
            use_pass_z=getattr(view_layer, "use_pass_z", None),
            use_pass_normal=getattr(view_layer, "use_pass_normal", None),
            use_snap=getattr(tool, "use_snap", None),
            use_transform_data_origin=getattr(tool, "use_transform_data_origin", None),
            mesh_select_mode=tuple(tool.mesh_select_mode) if tool is not None and hasattr(tool, "mesh_select_mode") else None,
        )

    def restore(self, bpy_api=None) -> None:
        api = _api(bpy_api)
        context = api.context
        scene = context.scene

        current = context.view_layer.objects.active
        if current is not None and getattr(current, "mode", "OBJECT") != "OBJECT":
            try:
                api.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        for obj in tuple(getattr(context, "selected_objects", ())):
            try:
                obj.select_set(False)
            except Exception:
                pass

        get_object = api.data.objects.get
        selected = []
        for name in self.selected_objects:
            obj = get_object(name)
            if obj is not None:
                obj.select_set(True)
                selected.append(obj)

        active = get_object(self.active_object) if self.active_object else None
        context.view_layer.objects.active = active

        scene.frame_set(self.frame)
        scene.camera = get_object(self.camera) if self.camera else None
        scene.render.filepath = self.render_filepath
        scene.render.image_settings.file_format = self.render_format
        if self.render_engine is not None:
            scene.render.engine = self.render_engine
        if self.render_resolution_x is not None:
            scene.render.resolution_x = self.render_resolution_x
        if self.render_resolution_y is not None:
            scene.render.resolution_y = self.render_resolution_y
        if self.render_resolution_percentage is not None:
            scene.render.resolution_percentage = self.render_resolution_percentage
        if self.render_film_transparent is not None:
            scene.render.film_transparent = self.render_film_transparent
        display = getattr(scene, "display", None)
        shading = getattr(display, "shading", None)
        if shading is not None:
            if self.shading_light is not None:
                shading.light = self.shading_light
            if self.shading_color_type is not None:
                shading.color_type = self.shading_color_type
        if hasattr(scene, "compositing_node_group"):
            scene.compositing_node_group = self.compositing_node_group
        view_layer = getattr(context, "view_layer", None)
        if view_layer is not None:
            if self.use_pass_z is not None and hasattr(view_layer, "use_pass_z"):
                view_layer.use_pass_z = self.use_pass_z
            if self.use_pass_normal is not None and hasattr(view_layer, "use_pass_normal"):
                view_layer.use_pass_normal = self.use_pass_normal

        tool = getattr(scene, "tool_settings", None)
        if tool is not None:
            if self.use_snap is not None and hasattr(tool, "use_snap"):
                tool.use_snap = self.use_snap
            if self.use_transform_data_origin is not None and hasattr(tool, "use_transform_data_origin"):
                tool.use_transform_data_origin = self.use_transform_data_origin
            if self.mesh_select_mode is not None and hasattr(tool, "mesh_select_mode"):
                tool.mesh_select_mode = self.mesh_select_mode

        if active is not None and self.mode != "OBJECT":
            try:
                api.ops.object.mode_set(mode=self.mode)
            except Exception as exc:
                raise RuntimeError(f"Failed to restore Blender mode {self.mode}: {exc}") from exc


class BlenderStateGuard:
    """Restore a captured state on normal exit or handler failure."""

    def __init__(self, *, bpy_api=None, restore: bool = True):
        self.bpy_api = bpy_api
        self.restore_enabled = restore
        self.snapshot: BlenderStateSnapshot | None = None

    def __enter__(self) -> "BlenderStateGuard":
        self.snapshot = BlenderStateSnapshot.capture(self.bpy_api)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.restore_enabled and self.snapshot is not None:
            self.snapshot.restore(self.bpy_api)
        return False