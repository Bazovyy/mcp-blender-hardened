"""Render-related command handlers."""

import math
import os
import tempfile

import bpy

from .. import compat
from ..utils import get_object_or_error
from ..validation import (
    require_param,
    validate_enum,
    validate_filepath,
)


class RenderHandlersMixin:
    """Mixin for render-related handlers."""

    def _handle_render_image(self, params: dict) -> dict:
        """Render current frame to file."""
        output_path = validate_filepath(
            require_param(params, "output_path", str),
            "output_path"
        )
        valid_formats = ["PNG", "JPEG", "BMP", "TIFF", "OPEN_EXR", "HDR"]
        file_format = validate_enum(
            params.get("file_format", "PNG"),
            "file_format",
            valid_formats
        )

        scene = bpy.context.scene
        scene.render.image_settings.file_format = file_format
        scene.render.filepath = output_path

        bpy.ops.render.render(write_still=True)
        return {"output_path": output_path}


    def _handle_render_animation(self, params: dict) -> dict:
        """Render animation."""
        output_path = params["output_path"]
        file_format = params.get("file_format", "PNG").upper()

        scene = bpy.context.scene
        scene.render.image_settings.file_format = file_format
        scene.render.filepath = output_path

        if params.get("start_frame"):
            scene.frame_start = params["start_frame"]
        if params.get("end_frame"):
            scene.frame_end = params["end_frame"]

        bpy.ops.render.render(animation=True)
        return {"output_path": output_path}


    def _handle_render_set_engine(self, params: dict) -> dict:
        """Set render engine."""
        engine = params["engine"].upper()

        # Blender 5.2 uses BLENDER_EEVEE; accept old aliases without exposing them in schema.
        if engine in ("EEVEE", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
            engine = "BLENDER_EEVEE"
        engine = validate_enum(engine, "engine", ["BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"])
        bpy.context.scene.render.engine = engine
        return {"engine": bpy.context.scene.render.engine}


    def _handle_render_set_resolution(self, params: dict) -> dict:
        """Set render resolution."""
        scene = bpy.context.scene
        scene.render.resolution_x = params["width"]
        scene.render.resolution_y = params["height"]
        scene.render.resolution_percentage = params.get("percentage", 100)
        return {
            "width": scene.render.resolution_x,
            "height": scene.render.resolution_y,
            "percentage": scene.render.resolution_percentage,
        }


    def _handle_render_screenshot(self, params: dict) -> dict:
        """Capture viewport screenshot."""
        output_path = params["output_path"]
        bpy.ops.screen.screenshot_area(filepath=output_path)
        return {"output_path": output_path}

    # ========== Export Handlers ==========


    def _handle_render_multi_angle(self, params: dict) -> dict:
        """Render an object from multiple angles for visual feedback."""
        import mathutils

        object_name = params.get("object_name")
        angles = params.get("angles", ["front", "right", "top", "perspective"])
        resolution = params.get("resolution", [512, 512])
        output_dir = params.get("output_dir")

        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="mcp_render_")

        os.makedirs(output_dir, exist_ok=True)

        # Find target object
        if object_name:
            obj = get_object_or_error(object_name)
        else:
            # Use all mesh objects
            obj = None

        # Compute bounding box center and size
        if obj:
            bbox_corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
        else:
            bbox_corners = []
            for o in bpy.context.scene.objects:
                if o.type == "MESH":
                    bbox_corners.extend(
                        o.matrix_world @ mathutils.Vector(c) for c in o.bound_box
                    )

        if not bbox_corners:
            return {"success": False, "error": "No mesh objects found to render"}

        min_co = mathutils.Vector((
            min(c.x for c in bbox_corners),
            min(c.y for c in bbox_corners),
            min(c.z for c in bbox_corners),
        ))
        max_co = mathutils.Vector((
            max(c.x for c in bbox_corners),
            max(c.y for c in bbox_corners),
            max(c.z for c in bbox_corners),
        ))
        center = (min_co + max_co) / 2
        bbox_size = max_co - min_co
        distance = bbox_size.length * 1.5

        if distance < 0.01:
            distance = 5.0

        # Camera angle definitions (position relative to center)
        angle_configs = {
            "front": {
                "location": mathutils.Vector((0, -distance, 0)) + center,
                "rotation": (math.radians(90), 0, 0),
                "ortho": True,
            },
            "right": {
                "location": mathutils.Vector((distance, 0, 0)) + center,
                "rotation": (math.radians(90), 0, math.radians(90)),
                "ortho": True,
            },
            "top": {
                "location": mathutils.Vector((0, 0, distance)) + center,
                "rotation": (0, 0, 0),
                "ortho": True,
            },
            "perspective": {
                "location": mathutils.Vector((
                    distance * 0.7,
                    -distance * 0.7,
                    distance * 0.5,
                )) + center,
                "rotation": None,  # Use track_to
                "ortho": False,
            },
        }

        from ..state_guard import BlenderStateGuard

        scene = bpy.context.scene
        renders = {}
        temp_objects = []
        with BlenderStateGuard():
            try:
                scene.render.engine = "BLENDER_WORKBENCH"
                scene.render.resolution_x = int(resolution[0])
                scene.render.resolution_y = int(resolution[1])
                scene.render.resolution_percentage = 100
                scene.display.shading.light = "STUDIO"
                scene.display.shading.color_type = "MATERIAL"

                for angle_name in angles:
                    config = angle_configs.get(angle_name)
                    if not config:
                        continue
                    cam_data = bpy.data.cameras.new(f"_mcp_temp_cam_{angle_name}")
                    cam_obj = bpy.data.objects.new(f"_mcp_temp_cam_{angle_name}", cam_data)
                    bpy.context.collection.objects.link(cam_obj)
                    temp_objects.append(cam_obj)
                    cam_obj.location = config["location"]
                    if config["ortho"]:
                        cam_data.type = "ORTHO"
                        cam_data.ortho_scale = max(bbox_size.x, bbox_size.y, bbox_size.z) * 1.3
                        cam_obj.rotation_euler = config["rotation"]
                    else:
                        cam_data.type = "PERSP"
                        cam_data.lens = 50
                        direction = center - cam_obj.location
                        cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
                    scene.camera = cam_obj
                    filepath = os.path.join(output_dir, f"{angle_name}.png")
                    scene.render.filepath = filepath
                    scene.render.image_settings.file_format = "PNG"
                    bpy.ops.render.render(write_still=True)
                    renders[angle_name] = filepath
            finally:
                for temp_obj in temp_objects:
                    cam_data = temp_obj.data
                    if temp_obj.name in bpy.data.objects:
                        bpy.data.objects.remove(temp_obj, do_unlink=True)
                    if cam_data.name in bpy.data.cameras:
                        bpy.data.cameras.remove(cam_data)

        return {
            "success": True, "renders": renders, "output_dir": output_dir, "resolution": resolution,
        }

    # ========== Vision Analysis Handler ==========

