"""Startup helpers for IsolatedExtensionProcess."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from .ipc_protocol import recv_msg

logger = logging.getLogger(__name__)

_RUNTIME_ENV_KEYS = {
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMP", "TEMP", "TMPDIR",
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PROCESSOR_ARCHITECTURE",
}


def build_worker_command(proc, uid: str) -> tuple:
    iso_config = proc.config.get("process_isolation", {})
    worker_script = str(Path(__file__).parent / "isolation_worker.py")

    cmd = [sys.executable, worker_script]
    env = {key: value for key, value in os.environ.items() if key.upper() in _RUNTIME_ENV_KEYS}
    env["YU_ISO_SOCKET"] = proc._socket_path
    env["YU_ISO_EXT_NAME"] = proc.ext_name
    env["YU_ISO_EXT_DIR"] = str(proc.ext_dir)
    env["YU_ISO_EXT_ENTRY"] = proc.entry
    env["YU_ISO_PERMISSIONS"] = json.dumps(list(proc.granted_permissions))
    env["YU_ISO_SECCOMP"] = "1" if iso_config.get("seccomp", False) else "0"
    env["YU_ISO_NETNS"] = "1" if iso_config.get("network_namespace", False) else "0"
    env["YU_ISO_REVERSE_SOCKET"] = proc._reverse_socket_path
    env["YU_ISO_REVERSE_TOKEN"] = proc._reverse_token or ""
    env.pop("PYTHONPATH", None)
    for marker in (
        "YU_ISO_APPARMOR",
        "YU_ISO_OS_ENFORCED",
        "YU_ISO_SANDBOX_EXEC",
        "YU_ISO_WIN_RESTRICTED",
    ):
        env.pop(marker, None)

    extra_popen_kwargs: dict = {}
    try:
        from core.extensions_core.os_isolation import apply_os_isolation

        cmd, env, extra_popen_kwargs = apply_os_isolation(
            cmd=cmd,
            env=env,
            ext_name=proc.ext_name,
            ext_dir=proc.ext_dir,
            permissions=proc.granted_permissions,
            config=proc.config,
        )
    except Exception as exc:
        logger.warning("%s: OS isolation skipped: %s", proc.ext_name, exc)

    if getattr(proc, "require_os_isolation", False) and env.get("YU_ISO_OS_ENFORCED") != "1":
        raise RuntimeError("Required OS isolation is unavailable")

    return cmd, env, extra_popen_kwargs


def accept_connections(proc, worker_start_timeout: float) -> bool:
    try:
        proc._conn, _ = proc._server_sock.accept()
        proc._conn.settimeout(30.0)
    except TimeoutError:
        logger.error(
            "%s: Worker connection timeout%s",
            proc.ext_name,
            read_worker_stderr_snippet(proc),
        )
        proc.stop()
        return False
    except Exception as exc:
        logger.error("%s: Worker connection failed: %s", proc.ext_name, exc)
        proc.stop()
        return False

    try:
        hello = recv_msg(proc._conn, timeout=10.0)
        if (
            not hello
            or hello.get("method") != "hello"
            or hello.get("error")
            or hello.get("ext_name") != proc.ext_name
            or hello.get("pid") != proc._process.pid
            or not isinstance(hello.get("hooks"), list)
        ):
            logger.error("%s: Handshake failed", proc.ext_name)
            proc.stop()
            return False
    except Exception as exc:
        logger.error("%s: Handshake error: %s", proc.ext_name, exc)
        proc.stop()
        return False
    return True


def read_worker_stderr_snippet(proc) -> str:
    process = proc._process
    if not process or process.stderr is None:
        return ""
    try:
        if process.poll() is None:
            return ""
        data = process.stderr.read(4000)
    except Exception:
        return ""
    if not data:
        return ""
    text = data.decode("utf-8", "replace").strip() if isinstance(data, bytes) else str(data).strip()
    return f" (stderr: {text[:400]})" if text else ""
