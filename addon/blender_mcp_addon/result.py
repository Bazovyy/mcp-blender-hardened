"""Wire-level success/error envelope helpers."""

from __future__ import annotations
from typing import Any

def ok(result: Any = None) -> dict:
    return {"ok": True, "result": result}

def fail(code: str, message: str, details: dict | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}

def normalize_handler_result(result: Any) -> dict:
    if isinstance(result, dict) and isinstance(result.get("ok"), bool):
        return result
    if isinstance(result, dict) and result.get("success") is False:
        message = result.get("error") or result.get("message") or "Handler reported failure"
        return fail("handler_failed", str(message), dict(result))
    return ok(result)
