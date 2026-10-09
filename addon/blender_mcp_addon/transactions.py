"""Operation identity and transaction metadata for Blender handler calls."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from uuid import uuid4


_current_operation: ContextVar["OperationTransaction | None"] = ContextVar("mcp_blender_operation", default=None)


@dataclass
class OperationTransaction:
    method: str
    risk_class: str = "normal"
    checkpoint_strategy: str = "none"
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "pending"
    result_state: str | None = None
    error: str | None = None
    requires_reacquire: bool = False
    _token: Token | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "OperationTransaction":
        self.status = "running"
        self._token = _current_operation.set(self)
        return self

    def mark_reacquire_boundary(self) -> None:
        """Mark that Blender ID references must be reacquired before reuse."""
        self.requires_reacquire = True

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is None:
            self.status = "completed"
            self.result_state = self.result_state or "completed"
        else:
            self.status = "failed"
            self.result_state = "failed"
            self.error = str(exc)
        if self._token is not None:
            _current_operation.reset(self._token)
            self._token = None
        return False


def current_operation() -> OperationTransaction | None:
    return _current_operation.get()