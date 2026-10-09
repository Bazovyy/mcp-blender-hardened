"""Host-side tests for the Blender addon socket/runtime boundary."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import socket
import sys
import types

import pytest


class _FakeTimers:
    def __init__(self):
        self.registered = []

    def register(self, callback, **kwargs):
        self.registered.append(callback)

    def unregister(self, callback):
        self.registered.remove(callback)

    def is_registered(self, callback):
        return callback in self.registered


def _install_fake_bpy():
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(timers=_FakeTimers(), version=(5, 2, 2), version_string="5.2.2 LTS")
    bpy.types = types.SimpleNamespace(Operator=object, Panel=object, PropertyGroup=object, Scene=type("Scene", (), {}))
    bpy.props = types.SimpleNamespace(
        StringProperty=lambda **kwargs: None,
        IntProperty=lambda **kwargs: None,
        BoolProperty=lambda **kwargs: None,
        PointerProperty=lambda **kwargs: None,
    )
    bpy.utils = types.SimpleNamespace(register_class=lambda cls: None, unregister_class=lambda cls: None)
    sys.modules["bpy"] = bpy
    return bpy


_FAKE_BPY = _install_fake_bpy()
ADDON_ROOT = Path(__file__).resolve().parents[1] / "addon"
if str(ADDON_ROOT) not in sys.path:
    sys.path.insert(0, str(ADDON_ROOT))

addon = importlib.import_module("blender_mcp_addon")
socket_server = importlib.import_module("blender_mcp_addon.socket_server")
# Do not make unrelated host-side tests believe they are running inside Blender.
sys.modules.pop("bpy", None)


class _Handlers:
    def __init__(self):
        self.calls = []

    def handle(self, method, params):
        self.calls.append((method, params))
        return {"handled": method}


class _ShortSendSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = bytearray()

    def send(self, data):
        n = min(self.chunks.pop(0), len(data))
        self.sent.extend(data[:n])
        return n


def _client_state(server):
    factory = getattr(server, "_new_client_state", None)
    return factory() if factory else b""


def test_process_clients_enqueues_without_calling_handler():
    handlers = _Handlers()
    server = socket_server.MCPSocketServer()
    server.handlers = handlers
    read_sock, write_sock = socket.socketpair()
    read_sock.setblocking(False)
    try:
        server.clients[read_sock] = _client_state(server)
        request = {"jsonrpc": "2.0", "id": "1", "method": "ping", "params": {}}
        write_sock.sendall((json.dumps(request) + "\n").encode())
        server._process_clients()
        assert handlers.calls == []
        assert len(server.dispatcher) == 1
    finally:
        read_sock.close()
        write_sock.close()


def test_oversized_unterminated_frame_disconnects_client():
    server = socket_server.MCPSocketServer()
    server.max_request_bytes = 16
    read_sock, write_sock = socket.socketpair()
    read_sock.setblocking(False)
    try:
        server.clients[read_sock] = _client_state(server)
        write_sock.sendall(b"x" * 32)
        server._process_clients()
        assert read_sock not in server.clients
    finally:
        read_sock.close()
        write_sock.close()


def test_partial_nonblocking_write_keeps_unsent_tail():
    server = socket_server.MCPSocketServer()
    fake = _ShortSendSocket([3, 100])
    state = server._new_client_state()
    state.send_buffer.extend(b"abcdef")
    server.clients[fake] = state
    server._flush_clients()
    assert bytes(state.send_buffer) == b"def"
    server._flush_clients()
    assert bytes(state.send_buffer) == b""
    assert bytes(fake.sent) == b"abcdef"


def test_timer_callback_reference_is_stable():
    server = socket_server.MCPSocketServer()
    callback = server._timer_callback
    assert callback is server._timer_callback


def test_start_operator_reports_start_failure(monkeypatch):
    class FailedServer:
        is_running = False
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def start(self):
            return False

    class ReportingOperator(addon.MCP_OT_StartServer):
        def __init__(self):
            self.messages = []
        def report(self, kinds, message):
            self.messages.append((kinds, message))

    monkeypatch.setattr(addon, "MCPSocketServer", FailedServer)
    addon._server = None
    props = types.SimpleNamespace(host="127.0.0.1", port=9877, allow_non_loopback=False)
    context = types.SimpleNamespace(scene=types.SimpleNamespace(mcp_server_props=props))
    op = ReportingOperator()
    assert op.execute(context) == {"CANCELLED"}
    assert any("failed" in message.lower() for _, message in op.messages)
    assert addon._server is None


def test_runtime_dispatcher_obeys_item_budget():
    runtime = importlib.import_module("blender_mcp_addon.runtime")
    handled = []
    responses = []

    class Handler:
        def handle(self, method, params):
            handled.append(method)
            return {"ok": method}

    dispatcher = runtime.MainThreadDispatcher(Handler(), lambda envelope, response: responses.append((envelope, response)))
    for i in range(3):
        dispatcher.enqueue(runtime.RequestEnvelope(str(i), f"m{i}", {}, object()))
    assert dispatcher.tick(max_items=2, time_budget_ms=100) == 2
    assert handled == ["m0", "m1"]
    assert len(dispatcher) == 1
    assert len(responses) == 2


def test_dispatcher_normalizes_handler_failures_to_wire_envelope():
    runtime = importlib.import_module("blender_mcp_addon.runtime")
    responses = []
    class Handler:
        def handle(self, method, params):
            if method == "reported":
                return {"success": False, "error": "bad input"}
            raise ValueError("boom")
    dispatcher = runtime.MainThreadDispatcher(Handler(), lambda envelope, response: responses.append(response))
    dispatcher.enqueue(runtime.RequestEnvelope("1", "reported", {}, object()))
    dispatcher.enqueue(runtime.RequestEnvelope("2", "raised", {}, object()))
    assert dispatcher.tick(max_items=2, time_budget_ms=100) == 2
    assert responses[0]["result"]["ok"] is False
    assert responses[0]["result"]["error"]["code"] == "handler_failed"
    assert responses[1]["result"]["ok"] is False
    assert responses[1]["result"]["error"]["code"] == "handler_exception"
