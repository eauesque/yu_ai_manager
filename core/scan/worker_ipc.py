"""Scan worker IPC -- JSON file-based inter-process communication."""

from typing import Any

from core.worker_ipc import (
    clear_pid as _clear_pid,
)
from core.worker_ipc import (
    clear_progress as _clear_progress,
)
from core.worker_ipc import (
    is_process_alive,  # noqa: F401  re-export for scan_worker_job
    make_worker_ipc_paths,
)
from core.worker_ipc import (
    is_worker_running as _is_worker_running,
)
from core.worker_ipc import (
    read_pid as _read_pid,
)
from core.worker_ipc import (
    read_progress as _read_progress,
)
from core.worker_ipc import (
    signal_stop as _signal_stop,
)
from core.worker_ipc import (
    write_pid as _write_pid,
)
from core.worker_ipc import (
    write_progress as _write_progress,
)

_PATHS = make_worker_ipc_paths("yu-scan")


def write_pid(pid: int) -> None:
    _write_pid(_PATHS, pid)


def read_pid() -> int | None:
    return _read_pid(_PATHS)


def clear_pid() -> None:
    _clear_pid(_PATHS)


def write_progress(data: dict[str, Any]) -> None:
    _write_progress(_PATHS, data)


def read_progress() -> dict[str, Any] | None:
    return _read_progress(_PATHS)


def clear_progress() -> None:
    _clear_progress(_PATHS)


def is_worker_running() -> bool:
    return _is_worker_running(_PATHS)


def signal_stop() -> bool:
    return _signal_stop(_PATHS)
