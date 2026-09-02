"""IsolatedExtensionProcess -- manages a sandboxed extension worker."""

from __future__ import annotations

import logging
import os
import socket
import struct
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .ipc_protocol import IPCError, recv_msg, send_msg, serialize_args
from .isolated_process_lifecycle import cleanup_socket, stop_process
from .isolated_process_lifecycle import is_alive as is_alive_impl
from .isolated_process_rpc import IsolatedProcessRPCMixin
from .isolated_process_spawn import accept_connections, build_worker_command

logger = logging.getLogger(__name__)
_WORKER_START_TIMEOUT = 30.0
_MAX_REJECTED_REVERSE_PEERS = 8
_HEARTBEAT_INTERVAL = 60.0


class IsolatedExtensionProcess(IsolatedProcessRPCMixin):
    """Manages an extension running in an isolated worker process."""

    def __init__(
        self,
        ext_name: str,
        ext_dir: Path,
        entry: str,
        granted_permissions: set,
        config: dict,
        require_os_isolation: bool = False,
    ) -> None:
        self.ext_name = ext_name
        self.ext_dir = ext_dir
        self.entry = entry
        self.granted_permissions = frozenset(granted_permissions)
        self.config = config
        self.require_os_isolation = require_os_isolation
        self._process: subprocess.Popen | None = None
        self._socket_path: str | None = None
        self._reverse_socket_path: str | None = None
        self._conn: socket.socket | None = None
        self._server_sock: socket.socket | None = None
        self._reverse_server_sock: socket.socket | None = None
        self._reverse_conn: socket.socket | None = None
        self._reverse_token: str | None = None
        self._rpc_server_thread: threading.Thread | None = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._alive = False

    def start(self) -> bool:
        if self._alive:
            return True

        uid = uuid.uuid4().hex[:8]
        tmpdir = tempfile.gettempdir()
        prefix = f"yu_ext_{self.ext_name}_{os.getpid()}_{uid}"
        self._socket_path = os.path.join(tmpdir, f"{prefix}.sock")
        self._reverse_socket_path = os.path.join(tmpdir, f"{prefix}_rev.sock")
        self._reverse_token = uuid.uuid4().hex

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self._socket_path)
        os.chmod(self._socket_path, 0o600)
        self._server_sock.listen(1)
        self._server_sock.settimeout(_WORKER_START_TIMEOUT)

        self._reverse_server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._reverse_server_sock.bind(self._reverse_socket_path)
        os.chmod(self._reverse_socket_path, 0o600)
        self._reverse_server_sock.listen(1)
        self._reverse_server_sock.settimeout(_WORKER_START_TIMEOUT)

        try:
            cmd, env, extra_popen_kwargs = build_worker_command(self, uid)
            self._process = subprocess.Popen(
                cmd,
                env=env,
                cwd=str(self.ext_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **extra_popen_kwargs,
            )
        except Exception as exc:
            logger.error("%s: Worker startup failed: %s", self.ext_name, exc)
            cleanup_socket(self)
            return False

        if not accept_connections(self, _WORKER_START_TIMEOUT):
            return False

        self._alive = True
        try:
            self._reverse_conn = self._accept_reverse_connection()
        except Exception as exc:
            logger.error(
                "%s: Reverse connection failed: %s",
                self.ext_name,
                exc,
            )
            self.stop()
            return False

        self._rpc_server_thread = self._start_rpc_server()
        logger.info("%s: Isolated process started (PID=%s)", self.ext_name, self._process.pid)
        return True

    def _accept_reverse_connection(self) -> socket.socket:
        if self._process is None or self._reverse_server_sock is None or self._reverse_token is None:
            raise RuntimeError("reverse channel is not initialized")
        deadline = time.monotonic() + _WORKER_START_TIMEOUT
        rejected_peers = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IPCError("reverse channel startup deadline exceeded")
            if rejected_peers >= _MAX_REJECTED_REVERSE_PEERS:
                raise IPCError("reverse channel peer rejection limit exceeded")
            self._reverse_server_sock.settimeout(remaining)
            connection, _ = self._reverse_server_sock.accept()
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise IPCError("reverse channel startup deadline exceeded")
                handshake_timeout = min(5.0, remaining)
                connection.settimeout(handshake_timeout)
                if hasattr(socket, "SO_PEERCRED"):
                    credentials = connection.getsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_PEERCRED,
                        struct.calcsize("3i"),
                    )
                    peer_pid, _uid, _gid = struct.unpack("3i", credentials)
                    if peer_pid != self._process.pid:
                        raise IPCError("reverse channel peer PID mismatch")
                hello = recv_msg(connection, timeout=handshake_timeout)
                if hello != {
                    "method": "reverse.hello",
                    "ext_name": self.ext_name,
                    "pid": self._process.pid,
                    "token": self._reverse_token,
                }:
                    raise IPCError("reverse channel handshake mismatch")
                return connection
            except Exception:
                connection.close()
                rejected_peers += 1
                logger.warning("%s: Rejected reverse channel peer", self.ext_name)

    def stop(self) -> None:
        stop_process(self)

    def is_alive(self) -> bool:
        return is_alive_impl(self)

    def call_hook(self, hook_name: str, args: list, kwargs: dict) -> Any:
        if not self.is_alive():
            raise IPCError(f"{self.ext_name}: Process is not running")
        return self._rpc_call(
            "hook.call",
            {
                "hook_name": hook_name,
                "args": serialize_args(args),
                "kwargs": serialize_args(kwargs),
            },
        )

    def _rpc_call(self, method: str, params: dict, timeout: float = 30.0) -> Any:
        with self._lock:
            request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self._next_id(),
            }
            try:
                send_msg(self._conn, request)
                response = recv_msg(self._conn, timeout=timeout)
            except Exception as exc:
                self._alive = False
                raise IPCError(f"RPC call failed: {exc}") from exc

        if response is None:
            self._alive = False
            raise IPCError("No response from worker")
        if "error" in response:
            err = response["error"]
            raise IPCError(f"RPC error {err.get('code', -1)}: {err.get('message', 'unknown')}")
        return response.get("result")

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
