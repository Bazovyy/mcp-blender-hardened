"""Non-blocking TCP transport for the Blender MCP addon."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import json
import socket
import traceback
from typing import Any

import bpy

from .handlers import CommandHandlers
from .jobs import tick_jobs
from .runtime import MainThreadDispatcher, RequestEnvelope
from .temp_assets import get_temp_asset_manager


@dataclass(slots=True)
class ClientState:
    recv_buffer: bytearray = field(default_factory=bytearray)
    send_buffer: bytearray = field(default_factory=bytearray)


class MCPSocketServer:
    """TCP transport that queues Blender work for bounded main-thread dispatch."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9877,
        *,
        allow_non_loopback: bool = False,
        max_request_bytes: int = 1_048_576,
    ):
        self.host = host
        self.port = port
        self.allow_non_loopback = allow_non_loopback
        self.max_request_bytes = max_request_bytes
        self.socket: socket.socket | None = None
        self.clients: dict[Any, ClientState] = {}
        self.is_running = False
        self.handlers = CommandHandlers()
        self.dispatcher = MainThreadDispatcher(self.handlers, self._queue_response)
        self._timer_registered = False
        self._timer_callback = self._tick
        self._restart_requested = False

    @property
    def client_count(self) -> int:
        return len(self.clients)

    def _host_is_loopback(self) -> bool:
        if self.host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False

    def _open_listener(self) -> socket.socket:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.setblocking(False)
        listener.bind((self.host, self.port))
        listener.listen(5)
        return listener

    def start(self) -> bool:
        if self.is_running:
            return False
        if not self.allow_non_loopback and not self._host_is_loopback():
            print("Failed to start MCP server: non-loopback bind requires explicit unsafe opt-in")
            return False
        try:
            self.socket = self._open_listener()
            self.is_running = True
            if not self._timer_registered:
                bpy.app.timers.register(self._timer_callback, persistent=True)
                self._timer_registered = True
            print(f"MCP Server started on {self.host}:{self.port}")
            return True
        except Exception as exc:
            print(f"Failed to start MCP server: {exc}")
            if self.socket is not None:
                self.socket.close()
                self.socket = None
            self.is_running = False
            return False

    def stop(self) -> None:
        self.is_running = False
        self._restart_requested = False
        for client in list(self.clients):
            self._disconnect_client(client)
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        if self._timer_registered:
            try:
                bpy.app.timers.unregister(self._timer_callback)
            except Exception:
                pass
            self._timer_registered = False
        print("MCP Server stopped")

    def request_restart(self) -> None:
        """Schedule a listener restart after the current response is flushed."""
        self._restart_requested = True

    def _restart_listener(self) -> None:
        self._restart_requested = False
        for client in list(self.clients):
            self._disconnect_client(client)
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
        try:
            self.socket = self._open_listener()
            print(f"MCP Server listener restarted on {self.host}:{self.port}")
        except Exception as exc:
            print(f"Failed to restart MCP server listener: {exc}")
            self.socket = None
            self.is_running = False

    def _tick(self) -> float | None:
        if not self.is_running:
            self._timer_registered = False
            return None
        try:
            self._accept_clients()
            self._process_clients()
            self.dispatcher.tick(max_items=8, time_budget_ms=8.0)
            tick_jobs(max_jobs=4, time_budget_ms=4.0)
            get_temp_asset_manager().maybe_cleanup()
            self._flush_clients()
            if self._restart_requested and all(not state.send_buffer for state in self.clients.values()):
                self._restart_listener()
        except Exception as exc:
            print(f"MCP Server tick error: {exc}")
            traceback.print_exc()
        return 0.01

    def _new_client_state(self) -> ClientState:
        return ClientState()

    def _accept_clients(self) -> None:
        if self.socket is None:
            return
        while True:
            try:
                client, addr = self.socket.accept()
                client.setblocking(False)
                self.clients[client] = self._new_client_state()
                print(f"MCP client connected: {addr}")
            except BlockingIOError:
                break
            except Exception as exc:
                print(f"Error accepting client: {exc}")
                break

    def _disconnect_client(self, client: Any) -> None:
        self.clients.pop(client, None)
        try:
            client.close()
        except Exception:
            pass

    def _process_clients(self) -> None:
        for client, state in list(self.clients.items()):
            try:
                try:
                    data = client.recv(65536)
                except BlockingIOError:
                    data = None
                except (ConnectionResetError, OSError):
                    self._disconnect_client(client)
                    continue

                if data == b"":
                    self._disconnect_client(client)
                    continue
                if data:
                    state.recv_buffer.extend(data)

                if len(state.recv_buffer) > self.max_request_bytes and b"\n" not in state.recv_buffer:
                    self._disconnect_client(client)
                    continue

                while client in self.clients and b"\n" in state.recv_buffer:
                    raw_line, remainder = bytes(state.recv_buffer).split(b"\n", 1)
                    state.recv_buffer[:] = remainder
                    if len(raw_line) > self.max_request_bytes:
                        self._disconnect_client(client)
                        break
                    if raw_line.strip():
                        self._parse_and_enqueue(client, raw_line)
            except Exception as exc:
                print(f"Error processing client: {exc}")
                traceback.print_exc()
                self._disconnect_client(client)

    def _parse_and_enqueue(self, client: Any, data: bytes) -> None:
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._append_response(client, {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
                "id": None,
            })
            return

        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        if not method:
            self._append_response(client, {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid request: missing method"},
                "id": msg_id,
            })
            return
        self.dispatcher.enqueue(RequestEnvelope(msg_id, method, params, client))

    def _queue_response(self, envelope: RequestEnvelope, response: dict) -> None:
        self._append_response(envelope.client, response)
        if envelope.method == "server_restart" and "error" not in response:
            self.request_restart()

    def _append_response(self, client: Any, response: dict) -> None:
        state = self.clients.get(client)
        if state is None:
            return
        encoded = (json.dumps(response, default=self._json_default) + "\n").encode("utf-8")
        state.send_buffer.extend(encoded)

    def _flush_clients(self) -> None:
        for client, state in list(self.clients.items()):
            if not state.send_buffer:
                continue
            try:
                sent = client.send(state.send_buffer)
                if sent > 0:
                    del state.send_buffer[:sent]
                elif sent == 0:
                    self._disconnect_client(client)
            except BlockingIOError:
                continue
            except (ConnectionResetError, BrokenPipeError, OSError):
                self._disconnect_client(client)

    @staticmethod
    def _json_default(obj: Any):
        if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, dict)):
            return list(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")