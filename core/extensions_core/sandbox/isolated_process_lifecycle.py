"""Lifecycle helpers for IsolatedExtensionProcess."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess

from .ipc_protocol import send_msg

logger = logging.getLogger(__name__)


def stop_process(proc) -> None:
    proc._alive = False

    if proc._conn:
        with contextlib.suppress(Exception):
            send_msg(
                proc._conn,
                {
                    "jsonrpc": "2.0",
                    "method": "shutdown",
                    "params": {},
                    "id": proc._next_id(),
                },
            )
        with contextlib.suppress(Exception):
            proc._conn.close()
        proc._conn = None

    if proc._process and proc._process.poll() is None:
        try:
            proc._process.terminate()
            proc._process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc._process.kill()
            proc._process.wait(timeout=2.0)
        except Exception:
            # `proc._process = None` follows regardless, so a process that
            # survived both terminate and kill is orphaned without a word.
            logger.warning(
                "%s: isolated process may still be running", proc.ext_name, exc_info=True
            )
    proc._process = None

    for sock in (proc._reverse_conn, proc._server_sock, proc._reverse_server_sock):
        if sock:
            with contextlib.suppress(Exception):
                sock.close()
    proc._reverse_conn = None
    proc._server_sock = None
    proc._reverse_server_sock = None
    cleanup_socket(proc)

    try:
        from core.extensions_core.os_isolation import cleanup_os_isolation

        cleanup_os_isolation(proc.ext_name)
    except Exception:
        # Leftover OS-level isolation state accumulates silently otherwise.
        logger.warning(
            "%s: OS isolation was not cleaned up", proc.ext_name, exc_info=True
        )

    logger.info("%s: Isolated process stopped", proc.ext_name)


def is_alive(proc) -> bool:
    if not proc._alive:
        return False
    if proc._process and proc._process.poll() is not None:
        proc._alive = False
        return False
    return True


def cleanup_socket(proc) -> None:
    for path in (proc._socket_path, proc._reverse_socket_path):
        if path and os.path.exists(path):
            with contextlib.suppress(Exception):
                os.unlink(path)
