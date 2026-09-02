"""IPC protocol primitives for extension process isolation.

Length-prefixed JSON-RPC 2.0 messaging over Unix sockets,
plus argument serialization/deserialization helpers.
"""

from __future__ import annotations

import json
import socket
import struct
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

# IPC maximum message size (16 MB)
MAX_MSG_SIZE = 16 * 1024 * 1024


class IPCError(Exception):
    """IPC communication error."""


def send_msg(sock: socket.socket, data: dict) -> None:
    """Send a length-prefixed JSON message over a socket."""
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    if len(payload) > MAX_MSG_SIZE:
        raise IPCError(f"Message too large: {len(payload)} bytes")
    header = struct.pack("!I", len(payload))
    sock.sendall(header + payload)


def recv_msg(sock: socket.socket, timeout: float = 30.0) -> dict | None:
    """Receive a length-prefixed JSON message from a socket."""
    sock.settimeout(timeout)
    try:
        header = _recv_exact(sock, 4)
        if header is None:
            return None
        (length,) = struct.unpack("!I", header)
        if length > MAX_MSG_SIZE:
            raise IPCError(f"Message too large: {length} bytes")
        payload = _recv_exact(sock, length)
        if payload is None:
            return None
        return json.loads(payload.decode("utf-8"))
    except TimeoutError:
        return None
    except (json.JSONDecodeError, struct.error) as exc:
        raise IPCError(f"Invalid message: {exc}") from exc


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Receive exactly n bytes from a socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def serialize_args(obj: Any) -> Any:
    """Convert RPC arguments to JSON-serializable form."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        import base64
        return {"__type__": "bytes", "data": base64.b64encode(obj).decode("ascii")}
    if isinstance(obj, Path):
        return {"__type__": "path", "data": str(obj)}
    if isinstance(obj, (list, tuple)):
        return [serialize_args(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): serialize_args(v) for k, v in obj.items()}
    # Convert everything else to string
    return str(obj)


def deserialize_args(obj: Any) -> Any:
    """Restore deserialized RPC arguments to Python objects."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        t = obj.get("__type__")
        if t == "bytes":
            import base64
            return base64.b64decode(obj["data"])
        if t == "path":
            return Path(obj["data"])
        return {k: deserialize_args(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deserialize_args(x) for x in obj]
    return obj


class WorkerRPCClient:
    """Minimal reverse-channel client exposed through the worker SDK."""

    def __init__(self, connection_provider: Callable[[], socket.socket | None]):
        self._connection_provider = connection_provider
        self._request_id = 0
        self._lock = threading.Lock()

    def call(self, method: str, params: dict) -> Any:
        conn = self._connection_provider()
        if conn is None:
            raise IPCError("Worker service channel is unavailable")
        with self._lock:
            self._request_id += 1
            send_msg(conn, {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self._request_id,
            })
            response = recv_msg(conn)
        if response is None:
            raise IPCError("Worker service channel closed")
        if "error" in response:
            raise IPCError(response["error"].get("message", "Request rejected"))
        return deserialize_args(response.get("result"))


class ReadOnlyDBClient:
    """Public worker SDK client for parameterized read-only queries."""

    def __init__(self, rpc: WorkerRPCClient):
        self._rpc = rpc

    def query(self, sql: str, params: list | tuple | dict | None = None) -> list[dict]:
        if not isinstance(sql, str):
            raise TypeError("sql must be a string")
        values = [] if params is None else params
        if not isinstance(values, (list, tuple, dict)):
            raise TypeError("params must be a list, tuple, or dict")
        items = values.values() if isinstance(values, dict) else values
        if not all(isinstance(value, (str, int, float, bool, type(None))) for value in items):
            raise TypeError("params must contain only JSON scalar values")
        return self._rpc.call("db.query", {
            "sql": sql,
            "params": serialize_args(values),
        })
