from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PayloadFactory = Callable[[], dict[str, Any]]
FixtureFactory = Callable[[], Any]
ResultAssert = Callable[[Any], None]
Cleanup = Callable[[], None]


@dataclass(frozen=True)
class ToolCase:
    name: str
    risk: str
    payload_factory: PayloadFactory
    fixture_factory: FixtureFactory | None = None
    assert_result: ResultAssert | None = None
    cleanup: Cleanup | None = None
    skip_external: str | None = None


def _empty_payload() -> dict[str, Any]:
    return {}


def _server_path() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "mcp_blender" / "server.py"


def discover_mcp_tool_names(server_path: Path | None = None) -> list[str]:
    path = server_path or _server_path()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = node.func.id if isinstance(node.func, ast.Name) else None
        if func_name != "Tool":
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                names.append(keyword.value.value)
                break
    return names


def _classify(name: str) -> tuple[str, str | None]:
    external_prefixes = ("blender_ai_", "blender_polyhaven_", "blender_refine_")
    if name.startswith(external_prefixes) or name == "blender_analyze_viewport":
        return "external", "requires an external AI/content provider or service"
    if any(token in name for token in ("sculpt_", "mesh_loop_cut", "mesh_knife_project", "mesh_edge_slide", "render_screenshot")):
        return "context_heavy", None
    if any(token in name for token in ("bake_", "physics_simulate", "render_animation")):
        return "blocking", None
    if any(token in name for token in ("_get_", "_list", "_info", "_inspect", "measure_", "validate_", "_check_", "_stats")):
        return "read", None
    return "bounded_mutation", None


def build_manifest() -> list[ToolCase]:
    cases: list[ToolCase] = []
    for name in discover_mcp_tool_names():
        risk, skip = _classify(name)
        cases.append(ToolCase(name=name, risk=risk, payload_factory=_empty_payload, skip_external=skip))
    return cases


def get_case(name: str) -> ToolCase:
    matches = [case for case in build_manifest() if case.name == name]
    if len(matches) != 1:
        raise KeyError(f"Expected exactly one manifest case for {name!r}, found {len(matches)}")
    return matches[0]