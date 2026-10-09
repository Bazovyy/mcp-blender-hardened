"""Safe Blender UI context discovery for context-sensitive operators."""

import bpy


def find_view3d_context():
    """Return a complete interactive VIEW_3D override, never a background pseudo-context."""
    if getattr(bpy.app, "background", False):
        return None
    wm = getattr(bpy.context, "window_manager", None)
    windows = getattr(wm, "windows", ()) if wm is not None else ()
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            override = {
                "window": window,
                "screen": screen,
                "area": area,
                "region": region,
            }
            scene = getattr(window, "scene", None)
            view_layer = getattr(window, "view_layer", None)
            if scene is not None:
                override["scene"] = scene
            if view_layer is not None:
                override["view_layer"] = view_layer
            return override
    return None
