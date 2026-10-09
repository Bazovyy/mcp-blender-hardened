"""Bounded main-thread request dispatcher for the Blender addon."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable


@dataclass(slots=True)
class RequestEnvelope:
    """One parsed JSON-RPC request awaiting Blender main-thread execution."""

    id: Any
    method: str
    params: dict[str, Any]
    client: Any


class MainThreadDispatcher:
    """Execute queued Blender handlers with a bounded per-tick budget."""

    def __init__(self, handlers: Any, response_callback: Callable[[RequestEnvelope, dict], None]):
        self.handlers = handlers
        self.response_callback = response_callback
        self._queue: deque[RequestEnvelope] = deque()

    def __len__(self) -> int:
        return len(self._queue)

    def enqueue(self, envelope: RequestEnvelope) -> None:
        self._queue.append(envelope)

    def tick(self, max_items: int = 8, time_budget_ms: float = 8.0) -> int:
        if max_items <= 0 or time_budget_ms <= 0:
            return 0

        started = perf_counter()
        processed = 0
        while self._queue and processed < max_items:
            elapsed_ms = (perf_counter() - started) * 1000.0
            if processed and elapsed_ms >= time_budget_ms:
                break

            envelope = self._queue.popleft()
            try:
                result = self.handlers.handle(envelope.method, envelope.params)
                response = {"jsonrpc": "2.0", "result": result, "id": envelope.id}
            except Exception as exc:
                response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(exc)},
                    "id": envelope.id,
                }
            self.response_callback(envelope, response)
            processed += 1

        return processed