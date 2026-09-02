"""Per-task generation state registry.

Replaces the module-global _progress_state with per-task UUID keyed state.
Thread-safe via threading.RLock (generate runs in blocking thread pool,
progress/cancel/cleanup in Quart async event loop).
"""
from __future__ import annotations

import contextlib
import threading
import time
import uuid as _uuid_mod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_lock = threading.RLock()
_tasks: dict[str, TaskEntry] = {}
_TTL_SECONDS = 60.0
_last_sweep: float = 0.0
_SWEEP_INTERVAL = 30.0  # seconds


@dataclass
class TaskEntry:
    task_id: str
    backend_id: str          # UUID or "__fallback__"
    base_url: str            # fixed at task creation; not re-resolved
    bridge_type: str         # "comfyui" or "sd-webui"
    cancel_fn: Callable | None = None
    status: str = "pending"  # pending → generating → done | error
    progress: int = 0
    step: int = 0
    total_steps: int = 0
    error_message: str | None = None
    completed_at: float | None = None


def create_task(task_id: str, backend_id: str, base_url: str, bridge_type: str) -> bool:
    """Register task. Returns False if task_id already exists (409 signal)."""
    with _lock:
        _sweep_expired()
        if task_id in _tasks:
            return False
        _tasks[task_id] = TaskEntry(
            task_id=task_id, backend_id=backend_id,
            base_url=base_url, bridge_type=bridge_type,
        )
        return True


def update_progress(task_id: str, progress: int, step: int = 0, total_steps: int = 0) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t.status = "generating"
            t.progress = progress
            t.step = step
            t.total_steps = total_steps


def complete_task(task_id: str) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t.status = "done"
            t.completed_at = time.monotonic()


def fail_task(task_id: str, message: str) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t.status = "error"
            t.error_message = message
            t.completed_at = time.monotonic()


def set_cancel_fn(task_id: str, fn: Callable) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t.cancel_fn = fn


def get_task_entry(task_id: str) -> TaskEntry | None:
    """Return task entry or None. For read-only inspection."""
    if not isinstance(task_id, str):
        return None
    with _lock:
        return _tasks.get(task_id)


def cancel_task(task_id: str) -> bool:
    if not isinstance(task_id, str):
        return False
    fn = None
    with _lock:
        t = _tasks.get(task_id)
        if not (t and t.cancel_fn):
            return False
        fn = t.cancel_fn
        t.status = "error"
        t.error_message = "cancelled"
        t.completed_at = time.monotonic()
    with contextlib.suppress(Exception):
        fn()
    return True


def get_progress_dict(task_id: str | None) -> dict[str, Any]:
    """Return progress dict.
    - task_id=None: legacy single-task, returns registered=True.
    - Unknown task_id: returns registered=False (pre-registration race is OK).
    """
    global _last_sweep
    if task_id is None:
        return {"status": "idle", "progress": 0, "step": 0, "total_steps": 0, "registered": True}
    if not isinstance(task_id, str):
        return {"status": "pending", "progress": 0, "registered": False}
    with _lock:
        now = time.monotonic()
        if now - _last_sweep > _SWEEP_INTERVAL:
            _sweep_expired()
            _last_sweep = now
        t = _tasks.get(task_id)
        if t is None:
            return {"status": "pending", "progress": 0, "registered": False}
        return {
            "status": t.status,
            "progress": t.progress,
            "step": t.step,
            "total_steps": t.total_steps,
            "registered": True,
            "error_message": t.error_message,
        }


def generate_task_id() -> str:
    return str(_uuid_mod.uuid4())


def _sweep_expired() -> None:
    now = time.monotonic()
    expired = [
        tid for tid, t in _tasks.items()
        if t.completed_at is not None and (now - t.completed_at) > _TTL_SECONDS
    ]
    for tid in expired:
        del _tasks[tid]
