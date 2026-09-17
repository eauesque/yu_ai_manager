"""Shared worker IPC helpers backed by per-user JSON files."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerIpcPaths:
    root: Path
    pid_file: Path
    progress_file: Path


def resolve_ipc_dir(name: str) -> Path:
    """Return a per-user runtime directory for a named worker."""
    override = os.environ.get("YU_SCAN_IPC_DIR", "")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg and os.path.isdir(xdg):
        return Path(xdg) / name
    suffix = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
    return Path(tempfile.gettempdir()) / f"{name}{suffix}"


def make_worker_ipc_paths(name: str) -> WorkerIpcPaths:
    root = resolve_ipc_dir(name)
    return WorkerIpcPaths(
        root=root,
        pid_file=root / "worker.pid",
        progress_file=root / "progress.json",
    )


def ensure_dir(paths: WorkerIpcPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)


def write_pid(paths: WorkerIpcPaths, pid: int) -> None:
    ensure_dir(paths)
    paths.pid_file.write_text(str(pid), encoding="utf-8")


def read_pid(paths: WorkerIpcPaths) -> int | None:
    try:
        if paths.pid_file.exists():
            return int(paths.pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pass
    return None


def clear_pid(paths: WorkerIpcPaths) -> None:
    with contextlib.suppress(OSError):
        paths.pid_file.unlink(missing_ok=True)


def write_progress(paths: WorkerIpcPaths, data: dict[str, Any]) -> None:
    """Atomically write progress JSON."""
    ensure_dir(paths)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(paths.root), suffix=".tmp")
        try:
            os.write(fd, json.dumps(data, ensure_ascii=False).encode("utf-8"))
            os.close(fd)
            fd = -1
            os.replace(tmp, str(paths.progress_file))
        except Exception:
            if fd != -1:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except Exception as exc:
        logger.warning("Progress write failed: %s", exc)


def read_progress(paths: WorkerIpcPaths) -> dict[str, Any] | None:
    try:
        if paths.progress_file.exists():
            return json.loads(paths.progress_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return None


def clear_progress(paths: WorkerIpcPaths) -> None:
    with contextlib.suppress(OSError):
        paths.progress_file.unlink(missing_ok=True)


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_worker_running(paths: WorkerIpcPaths) -> bool:
    pid = read_pid(paths)
    if pid is None:
        return False
    if not is_process_alive(pid):
        clear_pid(paths)
        clear_progress(paths)
        return False
    return True


def signal_stop(paths: WorkerIpcPaths) -> bool:
    pid = read_pid(paths)
    if pid is None or not is_process_alive(pid):
        clear_pid(paths)
        clear_progress(paths)
        return False
    try:
        if sys.platform == "win32":
            import subprocess

            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            os.kill(pid, signal.SIGTERM)
        return True
    except Exception as exc:
        logger.warning("Failed to signal worker PID %d: %s", pid, exc)
        return False


def get_process_memory_rss(pid: int) -> int | None:
    """Get process RSS memory usage (bytes). Supports Linux /proc."""
    if sys.platform == "win32":
        return None
    try:
        status_path = Path(f"/proc/{pid}/status")
        if status_path.exists():
            for line in status_path.read_text().splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
    except (OSError, ValueError):
        pass
    return None
