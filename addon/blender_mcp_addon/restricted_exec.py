"""Conservative AST-validated fallback for small Blender scripting tasks."""

from __future__ import annotations

import ast
import contextlib
import io
import math
from typing import Any


class RestrictedExecError(ValueError):
    pass


_FORBIDDEN_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "os", "sys", "subprocess", "socket", "pathlib",
    "builtins", "importlib", "ctypes", "shutil",
}
_FORBIDDEN_ATTRS = {
    "open_mainfile", "save_as_mainfile", "save_mainfile", "read_factory_settings",
    "quit_blender", "delete", "remove", "unlink", "load", "reload", "exec",
    "start_server", "stop_server", "restart_server", "undo", "redo", "undo_push",
}
_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom, ast.While, ast.FunctionDef, ast.AsyncFunctionDef,
    ast.ClassDef, ast.Lambda, ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith,
    ast.Await, ast.Yield, ast.YieldFrom,
)


def _safe_range(*args):
    value = range(*args)
    if len(value) > 100_000:
        raise RestrictedExecError("range is limited to 100000 iterations")
    return value


class _Validator(ast.NodeVisitor):
    def __init__(self):
        self.node_count = 0

    def generic_visit(self, node):
        self.node_count += 1
        if self.node_count > 512:
            raise RestrictedExecError("script is too complex")
        if isinstance(node, _FORBIDDEN_NODES):
            raise RestrictedExecError(f"{type(node).__name__} is not allowed")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id.startswith("__") or node.id in _FORBIDDEN_NAMES:
            raise RestrictedExecError(f"name '{node.id}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("_") or node.attr in _FORBIDDEN_ATTRS:
            raise RestrictedExecError(f"attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
            raise RestrictedExecError(f"call '{node.func.id}' is not allowed")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if isinstance(node.op, ast.Mult):
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, int) and abs(side.value) > 100_000:
                    raise RestrictedExecError("sequence multiplication is too large")
        if isinstance(node.op, ast.Pow) and isinstance(node.right, ast.Constant):
            if isinstance(node.right.value, (int, float)) and abs(node.right.value) > 32:
                raise RestrictedExecError("exponent is too large")
        self.generic_visit(node)


def validate_restricted_script(script: str) -> ast.AST:
    if not isinstance(script, str):
        raise RestrictedExecError("script must be a string")
    if len(script) > 32_768:
        raise RestrictedExecError("script exceeds 32768 characters")
    try:
        tree = ast.parse(script, mode="exec")
    except SyntaxError as exc:
        raise RestrictedExecError(f"invalid Python syntax: {exc}") from exc
    _Validator().visit(tree)
    return tree


def execute_restricted(script: str, bpy_api: Any) -> dict:
    """Execute a small validated script without imports/filesystem/process/network builtins."""
    tree = validate_restricted_script(script)
    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "float": float, "int": int, "len": len,
        "list": list, "max": max, "min": min, "print": print, "range": _safe_range,
        "reversed": reversed, "round": round, "set": set, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    }
    namespace = {"bpy": bpy_api, "math": math, "__builtins__": safe_builtins}
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = compile(tree, "<mcp-restricted-script>", "exec")
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exec(code, namespace, namespace)  # noqa: S102 - AST and builtins are restricted above.
    out = stdout.getvalue()
    err = stderr.getvalue()
    limit = 65_536
    if len(out) > limit:
        out = out[:limit] + "\n... (truncated)"
    if len(err) > limit:
        err = err[:limit] + "\n... (truncated)"
    return {"stdout": out, "stderr": err, "result": namespace.get("result")}