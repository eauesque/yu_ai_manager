"""Detect and kill processes occupying a port.

Windows: netstat -ano + taskkill
Unix:    lsof + os.kill(SIGKILL)
"""

import contextlib
import logging
import os
import signal
import subprocess
from pathlib import Path

from .detect import is_windows

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROCESS_MARKERS = (
    "yu_ai_manager",
    "web_ui.py",
    "yu-ai-manager",
)


def kill_stale_port(port: int) -> None:
    """Kill stale processes occupying the specified port."""
    my_pid = os.getpid()
    try:
        if is_windows():
            _kill_stale_port_windows(port, my_pid)
        else:
            _kill_stale_port_unix(port, my_pid)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def _looks_like_our_process(pid: int) -> bool:
    """Return True only for processes that appear to belong to this app."""
    if pid <= 0:
        return False
    try:
        if is_windows():
            cmdline = _read_windows_cmdline(pid)
            return _matches_process_markers(cmdline)
        cmdline = _read_unix_cmdline(pid)
        cwd = _read_unix_cwd(pid)
        return _matches_process_markers(cmdline) or _is_within_project(cwd)
    except Exception:
        return False


def _matches_process_markers(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _PROCESS_MARKERS)


def _is_within_project(path: str) -> bool:
    if not path:
        return False
    try:
        return Path(path).resolve().is_relative_to(_PROJECT_ROOT)
    except Exception:
        return False


def _read_unix_cmdline(pid: int) -> str:
    raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore")


def _read_unix_cwd(pid: int) -> str:
    return os.readlink(f"/proc/{pid}/cwd")


def _read_windows_cmdline(pid: int) -> str:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _kill_stale_port_windows(port: int, my_pid: int) -> None:
    """Windows: identify PID using the port via netstat -ano and taskkill."""
    out = subprocess.check_output(
        ["netstat", "-ano"], text=True, errors="replace", stderr=subprocess.DEVNULL,
    )
    for line in out.splitlines():
        if f":{port}" not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        try:
            pid = int(parts[-1])
        except (ValueError, IndexError):
            continue
        if pid == my_pid or pid == 0:
            continue
        if not _looks_like_our_process(pid):
            logger.info("Skipping non-app process PID %d on port %d", pid, port)
            continue
        logger.info(f"Killing stale process PID {pid} on port {port}")
        subprocess.call(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def _kill_stale_port_unix(port: int, my_pid: int) -> None:
    """Unix: identify PID using the port via lsof and send SIGKILL."""
    out = subprocess.check_output(
        ["lsof", "-ti", f":{port}"],
        text=True, stderr=subprocess.DEVNULL,
    )
    for token in out.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        if pid == my_pid:
            continue
        if not _looks_like_our_process(pid):
            logger.info("Skipping non-app process PID %d on port %d", pid, port)
            continue
        logger.info(f"Killing stale process PID {pid} on port {port}")
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)
