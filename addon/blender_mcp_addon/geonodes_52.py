"""Blender 5.2 Geometry Nodes interface/modifier helpers."""

from __future__ import annotations

from typing import Any, Iterable

import bpy


def iter_interface_sockets(group, in_out: str | None = None) -> Iterable[Any]:
    """Yield interface sockets, optionally filtered to INPUT or OUTPUT."""
    direction = in_out.upper() if in_out else None
    for item in group.interface.items_tree:
        if item.item_type != "SOCKET":
            continue
        if direction is None or item.in_out == direction:
            yield item


def _modifier_binding(modifier, identifier: str):
    inputs = getattr(getattr(modifier, "properties", None), "inputs", None)
    if inputs is None or not hasattr(inputs, identifier):
        return None
    return getattr(inputs, identifier)


def _plain_value(value: Any):
    if value is None:
        return None
    if hasattr(value, "name") and not isinstance(value, (str, bytes)):
        return value.name
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return list(value)
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def get_modifier_input(modifier, identifier: str):
    """Read a Blender 5.2 GN modifier interface input by socket identifier."""
    binding = _modifier_binding(modifier, identifier)
    if binding is None or not hasattr(binding, "value"):
        return None
    return _plain_value(binding.value)


def _resolve_id_value(socket_type: str | None, value: Any):
    if not isinstance(value, str):
        return value
    collections = {
        "NodeSocketObject": bpy.data.objects,
        "NodeSocketCollection": bpy.data.collections,
        "NodeSocketMaterial": bpy.data.materials,
        "NodeSocketImage": bpy.data.images,
    }
    collection = collections.get(socket_type or "")
    return collection.get(value) if collection is not None else value


def set_modifier_input(modifier, identifier: str, value: Any, socket_type: str | None = None) -> bool:
    """Set a Blender 5.2 GN modifier interface input by socket identifier."""
    binding = _modifier_binding(modifier, identifier)
    if binding is None or not hasattr(binding, "value"):
        return False
    resolved = _resolve_id_value(socket_type, value)
    if socket_type == "NodeSocketVector" and isinstance(resolved, (list, tuple)):
        resolved = tuple(float(v) for v in resolved[:3])
    elif socket_type == "NodeSocketColor" and isinstance(resolved, (list, tuple)):
        resolved = tuple(float(v) for v in resolved[:4])
    elif socket_type == "NodeSocketFloat":
        resolved = float(resolved)
    elif socket_type == "NodeSocketInt":
        resolved = int(resolved)
    elif socket_type == "NodeSocketBool":
        resolved = bool(resolved)
    binding.value = resolved
    return True


def find_socket(sockets, *, name: str | None = None, identifier: str | None = None, bl_idname: str | None = None):
    """Resolve a node socket by semantic fields rather than numeric position."""
    for socket in sockets:
        if name is not None and socket.name != name:
            continue
        if identifier is not None and socket.identifier != identifier:
            continue
        if bl_idname is not None and socket.bl_idname != bl_idname:
            continue
        return socket
    return None