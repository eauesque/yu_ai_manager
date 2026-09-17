"""Extension isolation worker process.

Spawned as a subprocess by the main process.
Communicates via Unix socket JSON-RPC 2.0.

Environment variables:
- YU_ISO_SOCKET: Unix socket path
- YU_ISO_EXT_NAME: Extension name
- YU_ISO_EXT_DIR: Extension directory
- YU_ISO_EXT_ENTRY: Entry point filename
- YU_ISO_PERMISSIONS: Granted permissions (JSON array)
- YU_ISO_SECCOMP: "1" to enable seccomp
- YU_ISO_NETNS: "1" to enable network namespace

Sandbox enforcement and helper logic is in isolation_worker_sandbox.py.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import socket
import struct
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="[iso-worker %(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("isolation_worker")

# Maximum message size (16 MB)
_MAX_MSG_SIZE = 16 * 1024 * 1024
def _send_msg(sock: socket.socket, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    header = struct.pack("!I", len(payload))
    sock.sendall(header + payload)


def _recv_msg(sock: socket.socket, timeout: float = 60.0) -> dict | None:
    sock.settimeout(timeout)
    try:
        header = _recv_exact(sock, 4)
        if header is None:
            return None
        (length,) = struct.unpack("!I", header)
        if length > _MAX_MSG_SIZE:
            return None
        payload = _recv_exact(sock, length)
        if payload is None:
            return None
        return json.loads(payload.decode("utf-8"))
    except TimeoutError:
        return None
    except Exception:
        return None


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def main() -> None:
    """Worker main entry point."""
    try:
        from .ipc_protocol import WorkerRPCClient
        from .isolation_worker_sandbox import (
            apply_network_namespace,
            apply_seccomp,
            handle_rpc_request,
            install_public_sdk,
            load_extension_module,
        )
    except ImportError:
        from ipc_protocol import WorkerRPCClient
        from isolation_worker_sandbox import (
            apply_network_namespace,
            apply_seccomp,
            handle_rpc_request,
            install_public_sdk,
            load_extension_module,
        )

    socket_path = os.environ.get("YU_ISO_SOCKET")
    ext_name = os.environ.get("YU_ISO_EXT_NAME")
    ext_dir = os.environ.get("YU_ISO_EXT_DIR")
    entry = os.environ.get("YU_ISO_EXT_ENTRY")
    permissions_json = os.environ.get("YU_ISO_PERMISSIONS", "[]")
    use_seccomp = os.environ.get("YU_ISO_SECCOMP", "0") == "1"
    use_netns = os.environ.get("YU_ISO_NETNS", "0") == "1"
    reverse_socket_path = os.environ.get("YU_ISO_REVERSE_SOCKET", "")
    reverse_token = os.environ.get("YU_ISO_REVERSE_TOKEN", "")

    if not all([socket_path, ext_name, ext_dir, entry]):
        logger.error("Required environment variables missing")
        sys.exit(1)

    permissions = set(json.loads(permissions_json))
    reverse_connection = {"socket": None}
    install_public_sdk(WorkerRPCClient(lambda: reverse_connection["socket"]))

    # Apply network namespace (execute before connecting)
    if use_netns and "network:internet" not in permissions:
        apply_network_namespace()

    # Connect to main process
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(socket_path)
    except Exception as exc:
        logger.error(f"Connection to main process failed: {exc}")
        sys.exit(1)

    # Load extension module
    try:
        module = load_extension_module(ext_name, ext_dir, entry)
        logger.info(f"Extension '{ext_name}' loaded")
    except Exception as exc:
        logger.error(f"Extension load failed: {exc}")
        _send_msg(conn, {
            "method": "hello",
            "error": str(exc),
        })
        conn.close()
        sys.exit(1)

    # Apply seccomp (after module loading)
    if use_seccomp:
        apply_seccomp()

    # Handshake
    _send_msg(conn, {
        "method": "hello",
        "ext_name": ext_name,
        "pid": os.getpid(),
        "hooks": [
            h for h in dir(module)
            if h.startswith("on_") and callable(getattr(module, h, None))
        ],
    })

    # Reverse socket connection (for ServiceRegistry access)
    reverse_conn = None
    if reverse_socket_path:
        try:
            reverse_conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            reverse_conn.connect(reverse_socket_path)
            _send_msg(reverse_conn, {
                "method": "reverse.hello",
                "ext_name": ext_name,
                "pid": os.getpid(),
                "token": reverse_token,
            })
            reverse_connection["socket"] = reverse_conn
            logger.info("Reverse socket connected (ServiceRegistry access available)")
        except Exception as exc:
            logger.warning(f"Reverse socket connection failed: {exc}")
            reverse_conn = None

    # SIGTERM handler
    running = True

    def _sigterm_handler(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _sigterm_handler)

    # Main loop: wait for requests
    logger.info(f"Worker loop started (PID={os.getpid()})")
    while running:
        try:
            request = _recv_msg(conn, timeout=120.0)
            if request is None:
                continue

            response = handle_rpc_request(module, request, ext_name)
            _send_msg(conn, response)

            if request.get("method") == "shutdown":
                running = False

        except Exception as exc:
            logger.error(f"Worker error: {exc}")
            running = False

    conn.close()
    if reverse_conn:
        with contextlib.suppress(Exception):
            reverse_conn.close()
    logger.info("Worker terminated")


if __name__ == "__main__":
    main()
