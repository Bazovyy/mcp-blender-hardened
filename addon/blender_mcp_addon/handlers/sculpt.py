"""Sculpting command handlers."""

import math
import os
import tempfile

import bpy

from ..context import find_view3d_context
from ..utils import (
    ensure_object_selected,
    get_object_or_error,
)
from ..validation import (
    ValidationError,
    require_param,
    validate_enum,
)


class SculptHandlersMixin:
    """Mixin for sculpting handlers."""

    def _handle_sculpt_setup(self, params: dict) -> dict:
        """Enter sculpt mode with configuration (multires, dyntopo, or simple)."""
        object_name = require_param(params, "object_name", str)
        mode = params.get("mode", "SIMPLE")
        mode = validate_enum(mode, "mode", ["MULTIRES", "DYNTOPO", "SIMPLE"])
        multires_levels = int(params.get("multires_levels", 3))
        dyntopo_detail = float(params.get("dyntopo_detail", 12.0))
        dyntopo_method = params.get("dyntopo_method", "RELATIVE")
        dyntopo_method = validate_enum(
            dyntopo_method, "dyntopo_method", ["RELATIVE", "CONSTANT", "BRUSH", "MANUAL"]
        )
        symmetry_axes = params.get("symmetry_axes", [])

        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh, got {obj.type}")

        # Ensure object is selected and active
        ensure_object_selected(obj)

        # Switch to object mode first if needed
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        result_info = {
            "success": True,
            "object": object_name,
            "sculpt_mode": mode,
        }

        # Set up MULTIRES if requested
        if mode == "MULTIRES":
            # Check if multires modifier already exists
            multires_mod = None
            for mod in obj.modifiers:
                if mod.type == "MULTIRES":
                    multires_mod = mod
                    break

            if multires_mod is None:
                multires_mod = obj.modifiers.new(name="Multires", type="MULTIRES")

            # Subdivide to the requested number of levels
            current_levels = multires_mod.total_levels
            levels_to_add = max(0, multires_levels - current_levels)
            for _ in range(levels_to_add):
                bpy.ops.object.multires_subdivide(
                    modifier=multires_mod.name, mode="CATMULL_CLARK"
                )

            multires_mod.sculpt_levels = multires_mod.total_levels
            result_info["multires_levels"] = multires_mod.total_levels
            result_info["modifier_name"] = multires_mod.name

        # Enter sculpt mode
        bpy.ops.object.mode_set(mode="SCULPT")

        # Set up DYNTOPO if requested
        if mode == "DYNTOPO":
            # Enable dynamic topology
            if not bpy.context.sculpt_object.use_dynamic_topology_sculpting:
                bpy.ops.sculpt.dynamic_topology_toggle()

            sculpt = bpy.context.tool_settings.sculpt
            sculpt.detail_size = dyntopo_detail

            # Map method name to Blender's detail_type_method
            method_map = {
                "RELATIVE": "RELATIVE",
                "CONSTANT": "CONSTANT",
                "BRUSH": "BRUSH",
                "MANUAL": "MANUAL",
            }
            sculpt.detail_type_method = method_map.get(dyntopo_method, "RELATIVE")

            result_info["dyntopo_detail"] = dyntopo_detail
            result_info["dyntopo_method"] = dyntopo_method

        # Set symmetry axes
        sculpt = bpy.context.tool_settings.sculpt
        sculpt.use_symmetry_x = "X" in [a.upper() for a in symmetry_axes]
        sculpt.use_symmetry_y = "Y" in [a.upper() for a in symmetry_axes]
        sculpt.use_symmetry_z = "Z" in [a.upper() for a in symmetry_axes]

        result_info["symmetry"] = {
            "x": sculpt.use_symmetry_x,
            "y": sculpt.use_symmetry_y,
            "z": sculpt.use_symmetry_z,
        }

        return result_info


    def _handle_sculpt_mesh_filter(self, params: dict) -> dict:
        """Apply a sculpt mesh filter without risking headless operator crashes."""
        object_name = require_param(params, "object_name", str)
        filter_type = validate_enum(
            require_param(params, "filter_type", str), "filter_type",
            ["SMOOTH", "SHARPEN", "ENHANCE_DETAIL", "SURFACE_NOISE", "INFLATE",
             "SPHERE", "RELAX", "RELAX_FACE_SETS", "ERASE_DISPLACEMENT"],
        )
        strength = float(params.get("strength", 1.0))
        iterations = max(1, int(params.get("iterations", 1)))
        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")

        # SMOOTH/RELAX have a safe data-level implementation and do not require
        # Sculpt mode or a VIEW_3D region. This is also safe in background tests.
        if filter_type in {"SMOOTH", "RELAX"}:
            import bmesh
            bm = bmesh.new()
            try:
                bm.from_mesh(obj.data)
                factor = max(0.0, min(1.0, abs(strength)))
                for _ in range(iterations):
                    bmesh.ops.smooth_vert(
                        bm, verts=list(bm.verts), factor=factor,
                        use_axis_x=True, use_axis_y=True, use_axis_z=True,
                    )
                bm.to_mesh(obj.data)
                obj.data.update()
            finally:
                bm.free()
            return {
                "success": True, "object": object_name, "filter_type": filter_type,
                "strength": strength, "iterations": iterations,
                "vertex_count": len(obj.data.vertices), "implementation": "bmesh",
            }

        override = find_view3d_context()
        if override is None:
            return {
                "success": False, "code": "context_required",
                "error": f"Sculpt mesh filter {filter_type} requires an interactive VIEW_3D context",
                "filter_type": filter_type,
            }
        with bpy.context.temp_override(**override):
            ensure_object_selected(obj)
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="SCULPT")
            for i in range(iterations):
                try:
                    bpy.ops.sculpt.mesh_filter(type=filter_type, strength=strength)
                except RuntimeError as exc:
                    return {
                        "success": False, "code": "operator_failed",
                        "error": f"Mesh filter failed on iteration {i + 1}: {exc}",
                        "completed_iterations": i,
                    }
        return {
            "success": True, "object": object_name, "filter_type": filter_type,
            "strength": strength, "iterations": iterations,
            "vertex_count": len(obj.data.vertices), "implementation": "view3d_operator",
        }


    def _handle_sculpt_mask_by_topology(self, params: dict) -> dict:
        """Create sculpt masks using Blender 5.2 mesh attributes where possible."""
        object_name = require_param(params, "object_name", str)
        mask_type = validate_enum(
            require_param(params, "mask_type", str), "mask_type",
            ["CAVITY", "ALL", "NONE", "RANDOM"],
        )
        invert = bool(params.get("invert", False))
        blur_iterations = max(0, int(params.get("blur_iterations", 0)))
        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")
        mesh = obj.data

        if mask_type == "CAVITY":
            override = find_view3d_context()
            if override is None:
                return {
                    "success": False, "code": "context_required",
                    "error": "CAVITY sculpt mask requires an interactive VIEW_3D context",
                }
            with bpy.context.temp_override(**override):
                ensure_object_selected(obj)
                if bpy.context.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="SCULPT")
                bpy.ops.sculpt.dirty_mask(dirty_only=False)
            attr = mesh.attributes.get(".sculpt_mask")
            if attr is None:
                return {"success": False, "code": "mask_unavailable", "error": "Cavity mask was not created"}
        else:
            attr = mesh.attributes.get(".sculpt_mask")
            if attr is None:
                attr = mesh.attributes.new(name=".sculpt_mask", type="FLOAT", domain="POINT")
            if mask_type == "ALL":
                values = [1.0] * len(attr.data)
            elif mask_type == "NONE":
                values = [0.0] * len(attr.data)
            else:
                import random
                rng = random.Random(int(params.get("seed", 0)))
                values = [rng.random() for _ in attr.data]
            for item, value in zip(attr.data, values):
                item.value = value

        attr = mesh.attributes.get(".sculpt_mask")
        values = [float(item.value) for item in attr.data]
        if invert:
            values = [1.0 - value for value in values]

        if blur_iterations and values:
            neighbors = [set() for _ in mesh.vertices]
            for edge in mesh.edges:
                a, b = edge.vertices
                neighbors[a].add(b); neighbors[b].add(a)
            for _ in range(blur_iterations):
                prior = values
                values = [
                    (prior[i] + sum(prior[j] for j in neighbors[i])) / (1 + len(neighbors[i]))
                    if neighbors[i] else prior[i]
                    for i in range(len(prior))
                ]
        for item, value in zip(attr.data, values):
            item.value = max(0.0, min(1.0, value))
        mesh.update()
        return {
            "success": True, "object": object_name, "mask_type": mask_type,
            "inverted": invert, "blur_iterations": blur_iterations,
            "implementation": "mesh_attribute" if mask_type != "CAVITY" else "view3d_operator",
        }


    def _handle_sculpt_face_set_create(self, params: dict) -> dict:
        """Create Blender 5.2 face-set attributes without removed sculpt enums."""
        object_name = require_param(params, "object_name", str)
        criteria = validate_enum(
            require_param(params, "criteria", str), "criteria",
            ["LINKED", "MATERIAL", "NORMAL", "SHARP_EDGES", "UV_ISLAND"],
        )
        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")
        mesh = obj.data

        attr = mesh.attributes.get(".sculpt_face_set")
        if attr is None:
            attr = mesh.attributes.new(name=".sculpt_face_set", type="INT", domain="FACE")

        if criteria == "LINKED":
            vertex_faces = [[] for _ in mesh.vertices]
            for poly in mesh.polygons:
                for vertex_index in poly.vertices:
                    vertex_faces[vertex_index].append(poly.index)
            unvisited = set(range(len(mesh.polygons)))
            groups = []
            while unvisited:
                seed = unvisited.pop()
                stack = [seed]
                group = {seed}
                while stack:
                    face_index = stack.pop()
                    for vertex_index in mesh.polygons[face_index].vertices:
                        for neighbor in vertex_faces[vertex_index]:
                            if neighbor in unvisited:
                                unvisited.remove(neighbor)
                                group.add(neighbor)
                                stack.append(neighbor)
                groups.append(group)
            for face_set_id, group in enumerate(groups, start=1):
                for face_index in group:
                    attr.data[face_index].value = face_set_id
            face_set_count = len(groups)
        elif criteria == "MATERIAL":
            material_ids = sorted({poly.material_index for poly in mesh.polygons})
            mapping = {material_id: i + 1 for i, material_id in enumerate(material_ids)}
            for poly in mesh.polygons:
                attr.data[poly.index].value = mapping[poly.material_index]
            face_set_count = len(material_ids)
        else:
            return {
                "success": False, "code": "unsupported_on_blender_5_2",
                "error": f"Face-set criteria {criteria} has no safe Blender 5.2 data-level implementation",
                "criteria": criteria,
            }
        mesh.update()
        return {
            "success": True, "object": object_name, "criteria": criteria,
            "face_set_count": face_set_count, "implementation": "mesh_attribute",
        }


    def _handle_sculpt_multires_reshape(self, params: dict) -> dict:
        """Manage multiresolution modifier levels."""
        object_name = require_param(params, "object_name", str)
        action = require_param(params, "action", str)
        action = validate_enum(
            action, "action",
            ["SUBDIVIDE", "UNSUBDIVIDE", "REBUILD", "APPLY_BASE", "DELETE_HIGHER", "DELETE_LOWER"],
        )

        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")

        # Find multires modifier
        multires_mod = None
        for mod in obj.modifiers:
            if mod.type == "MULTIRES":
                multires_mod = mod
                break

        if multires_mod is None:
            raise ValidationError(
                f"Object '{object_name}' has no Multires modifier. "
                "Use sculpt_setup with mode=MULTIRES first."
            )

        # Ensure object is selected and in appropriate mode
        ensure_object_selected(obj)
        if bpy.context.mode == "SCULPT":
            bpy.ops.object.mode_set(mode="OBJECT")

        mod_name = multires_mod.name
        levels_before = multires_mod.total_levels

        try:
            if action == "SUBDIVIDE":
                bpy.ops.object.multires_subdivide(
                    modifier=mod_name, mode="CATMULL_CLARK"
                )
            elif action == "UNSUBDIVIDE":
                bpy.ops.object.multires_unsubdivide(modifier=mod_name)
            elif action == "REBUILD":
                bpy.ops.object.multires_rebuild_subdiv(modifier=mod_name)
            elif action == "APPLY_BASE":
                bpy.ops.object.multires_base_apply(modifier=mod_name)
            elif action == "DELETE_HIGHER":
                bpy.ops.object.multires_higher_levels_delete(modifier=mod_name)
            elif action == "DELETE_LOWER":
                bpy.ops.object.multires_lower_levels_delete(modifier=mod_name)
        except RuntimeError as e:
            return {"error": f"Multires {action} failed: {str(e)}"}

        levels_after = multires_mod.total_levels

        return {
            "success": True,
            "object": object_name,
            "action": action,
            "modifier": mod_name,
            "levels_before": levels_before,
            "levels_after": levels_after,
            "sculpt_level": multires_mod.sculpt_levels,
            "render_level": multires_mod.render_levels,
        }


    def _handle_sculpt_to_retopo(self, params: dict) -> dict:
        """Pipeline: sculpt to retopologized mesh with optional displacement bake."""
        object_name = require_param(params, "object_name", str)
        method = params.get("method", "VOXEL_REMESH")
        method = validate_enum(method, "method", ["VOXEL_REMESH", "QUADRIFLOW"])
        target_polycount = int(params.get("target_polycount", 5000))
        bake_displacement = params.get("bake_displacement", True)
        displacement_resolution = int(params.get("displacement_resolution", 2048))
        output_path = params.get("output_displacement_path", "")

        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")

        # Exit sculpt mode if active
        ensure_object_selected(obj)
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        original_poly_count = len(obj.data.polygons)
        original_vert_count = len(obj.data.vertices)

        # Step 1: Duplicate the object for retopo
        bpy.ops.object.duplicate()
        retopo_obj = bpy.context.active_object
        retopo_name = f"{object_name}_retopo"
        retopo_obj.name = retopo_name

        # Step 2: Apply all modifiers on the retopo copy
        for mod in list(retopo_obj.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except RuntimeError:
                # Some modifiers can't be applied, remove them
                retopo_obj.modifiers.remove(mod)

        # Step 3: Remesh
        if method == "VOXEL_REMESH":
            # Estimate voxel size from target polycount and bounding box
            dims = retopo_obj.dimensions
            volume = dims.x * dims.y * dims.z
            if volume > 0 and target_polycount > 0:
                # Rough estimate: each voxel face ~ voxel_size^2, total surface ~ 6*volume^(2/3)
                surface_area = 6.0 * (volume ** (2.0 / 3.0))
                face_area = surface_area / target_polycount
                voxel_size = max(0.001, math.sqrt(face_area))
            else:
                voxel_size = 0.05

            retopo_obj.data.remesh_voxel_size = voxel_size
            retopo_obj.data.use_remesh_fix_poles = True
            if hasattr(retopo_obj.data, "use_remesh_smooth_normals"):
                retopo_obj.data.use_remesh_smooth_normals = True
            retopo_obj.data.use_remesh_preserve_volume = True

            ensure_object_selected(retopo_obj)
            bpy.ops.object.voxel_remesh()

        elif method == "QUADRIFLOW":
            ensure_object_selected(retopo_obj)
            try:
                bpy.ops.object.quadriflow_remesh(
                    target_faces=target_polycount,
                    use_preserve_sharp=True,
                    use_preserve_boundary=True,
                    use_mesh_symmetry=False,
                )
            except RuntimeError:
                # Quadriflow can fail on complex meshes, fall back to voxel
                retopo_obj.data.remesh_voxel_size = 0.05
                bpy.ops.object.voxel_remesh()

        retopo_poly_count = len(retopo_obj.data.polygons)
        retopo_vert_count = len(retopo_obj.data.vertices)

        # Step 4: Auto-UV unwrap the retopo mesh
        ensure_object_selected(retopo_obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")

        result = {
            "success": True,
            "original_object": object_name,
            "retopo_object": retopo_obj.name,
            "method": method,
            "original_polygons": original_poly_count,
            "original_vertices": original_vert_count,
            "retopo_polygons": retopo_poly_count,
            "retopo_vertices": retopo_vert_count,
            "reduction_ratio": round(retopo_poly_count / max(1, original_poly_count), 4),
            "uv_unwrapped": True,
        }

        # Step 5: Optionally bake displacement
        if bake_displacement:
            if not output_path:
                output_path = os.path.join(
                    tempfile.gettempdir(),
                    f"{object_name}_displacement.png",
                )

            try:
                # Create displacement image
                disp_image = bpy.data.images.new(
                    name=f"{object_name}_displacement",
                    width=displacement_resolution,
                    height=displacement_resolution,
                    float_buffer=True,
                )

                # Create a material with an image texture node for baking target
                bake_mat_name = f"_bake_disp_{object_name}"
                bake_mat = bpy.data.materials.new(name=bake_mat_name)
                bake_mat.use_nodes = True
                nodes = bake_mat.node_tree.nodes
                # Clear default nodes
                for node in nodes:
                    nodes.remove(node)

                # Add image texture node (active for baking)
                img_node = nodes.new(type="ShaderNodeTexImage")
                img_node.image = disp_image
                img_node.select = True
                nodes.active = img_node

                # Add principled BSDF and output for valid material
                bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
                output = nodes.new(type="ShaderNodeOutputMaterial")
                bake_mat.node_tree.links.new(bsdf.outputs[0], output.inputs[0])

                # Assign bake material to retopo object
                if len(retopo_obj.data.materials) == 0:
                    retopo_obj.data.materials.append(bake_mat)
                else:
                    retopo_obj.data.materials[0] = bake_mat

                # Set up bake settings
                scene = bpy.context.scene
                prev_engine = scene.render.engine
                scene.render.engine = "CYCLES"

                # Select original as active (source), retopo as selected (target)
                bpy.ops.object.select_all(action="DESELECT")
                retopo_obj.select_set(True)
                obj.select_set(True)
                bpy.context.view_layer.objects.active = retopo_obj

                # Configure bake
                scene.render.bake.use_selected_to_active = True
                scene.render.bake.cage_extrusion = max(obj.dimensions) * 0.1
                scene.render.bake.use_cage = False

                # Bake displacement
                bpy.ops.object.bake(type="DISPLACEMENT")

                # Save the image
                disp_image.filepath_raw = output_path
                disp_image.file_format = "PNG"
                disp_image.save()

                # Restore engine
                scene.render.engine = prev_engine

                # Clean up bake material
                retopo_obj.data.materials.clear()
                bpy.data.materials.remove(bake_mat)

                result["displacement_baked"] = True
                result["displacement_path"] = output_path
                result["displacement_resolution"] = displacement_resolution

            except Exception as e:
                result["displacement_baked"] = False
                result["displacement_error"] = str(e)

        return result


    def _handle_sculpt_extract_mask(self, params: dict) -> dict:
        """Extract masked faces from the Blender 5.2 `.sculpt_mask` point attribute."""
        import bmesh
        object_name = require_param(params, "object_name", str)
        thickness = float(params.get("thickness", 0.05))
        smooth_iterations = max(0, int(params.get("smooth_iterations", 2)))
        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")
        mesh = obj.data
        mask = mesh.attributes.get(".sculpt_mask")
        if mask is None or mask.domain != "POINT":
            return {"success": False, "code": "mask_missing", "error": "No .sculpt_mask point attribute found"}

        values = [float(item.value) for item in mask.data]
        selected = [
            poly for poly in mesh.polygons
            if poly.vertices and sum(values[i] for i in poly.vertices) / len(poly.vertices) > 0.5
        ]
        if not selected:
            return {"success": False, "code": "mask_empty", "error": "No masked faces found (threshold 0.5)"}

        used = sorted({vertex_index for poly in selected for vertex_index in poly.vertices})
        remap = {old: new for new, old in enumerate(used)}
        verts = [mesh.vertices[i].co.copy() for i in used]
        faces = [[remap[i] for i in poly.vertices] for poly in selected]
        new_mesh = bpy.data.meshes.new(f"{object_name}_extract")
        new_mesh.from_pydata(verts, [], faces)
        new_mesh.update()

        if smooth_iterations > 0 and new_mesh.vertices:
            bm = bmesh.new()
            try:
                bm.from_mesh(new_mesh)
                for _ in range(smooth_iterations):
                    bmesh.ops.smooth_vert(
                        bm, verts=list(bm.verts), factor=0.5,
                        use_axis_x=True, use_axis_y=True, use_axis_z=True,
                    )
                bm.to_mesh(new_mesh)
                new_mesh.update()
            finally:
                bm.free()

        new_obj = bpy.data.objects.new(f"{object_name}_extract", new_mesh)
        target_collection = obj.users_collection[0] if obj.users_collection else bpy.context.collection
        target_collection.objects.link(new_obj)
        new_obj.matrix_world = obj.matrix_world.copy()
        if thickness > 0:
            solidify = new_obj.modifiers.new(name="Solidify", type="SOLIDIFY")
            solidify.thickness = thickness
            solidify.offset = -1.0
        return {
            "success": True, "source_object": object_name,
            "extracted_object": new_obj.name, "thickness": thickness,
            "smooth_iterations": smooth_iterations,
            "vertex_count": len(new_mesh.vertices), "polygon_count": len(new_mesh.polygons),
            "implementation": "mesh_attribute",
        }


    def _handle_sculpt_remesh_voxel(self, params: dict) -> dict:
        """Apply voxel remesh to create uniform topology."""
        object_name = require_param(params, "object_name", str)
        voxel_size = float(params.get("voxel_size", 0.05))
        smooth = params.get("smooth", False)
        fix_poles = params.get("fix_poles", False)

        obj = get_object_or_error(object_name)
        if obj.type != "MESH":
            raise ValidationError(f"Object '{object_name}' is not a mesh")

        # Must be in object mode for voxel remesh
        ensure_object_selected(obj)
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        verts_before = len(obj.data.vertices)
        polys_before = len(obj.data.polygons)

        # Configure remesh settings
        obj.data.remesh_voxel_size = voxel_size
        obj.data.use_remesh_fix_poles = fix_poles
        if hasattr(obj.data, "use_remesh_smooth_normals"):
            obj.data.use_remesh_smooth_normals = smooth
        obj.data.use_remesh_preserve_volume = True

        # Apply voxel remesh
        try:
            bpy.ops.object.voxel_remesh()
        except RuntimeError as e:
            return {"error": f"Voxel remesh failed: {str(e)}"}

        verts_after = len(obj.data.vertices)
        polys_after = len(obj.data.polygons)

        # Optional post-smooth
        if smooth:
            # Apply a smooth modifier
            smooth_mod = obj.modifiers.new(name="_remesh_smooth", type="SMOOTH")
            smooth_mod.factor = 0.5
            smooth_mod.iterations = 2
            bpy.ops.object.modifier_apply(modifier=smooth_mod.name)

        return {
            "success": True,
            "object": object_name,
            "voxel_size": voxel_size,
            "fix_poles": fix_poles,
            "smooth": smooth,
            "vertices_before": verts_before,
            "vertices_after": verts_after,
            "polygons_before": polys_before,
            "polygons_after": polys_after,
        }


    # ========== Rigging & Armature Handlers ==========

