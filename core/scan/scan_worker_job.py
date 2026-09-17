"""Scan worker — FileBasedJob class and signal/parent monitoring."""

import logging
import threading
import time

from core.scan.worker_ipc import is_process_alive, write_progress
from core.worker_runtime import (
    install_cancel_signal_handlers,
)
from core.worker_runtime import (
    start_parent_monitor as _start_parent_monitor,
)

logger = logging.getLogger(__name__)

_PARENT_CHECK_INTERVAL = 60  # seconds


class FileBasedJob:
    """Job interface backed by JSON files for cross-process sharing.

    Mirrors the API of core.jobs_core.jobs_model.Job but writes
    progress to a JSON file so that a separate web_ui process can
    read it.
    """

    def __init__(self, job_id: str = "scan", label: str = "scan"):
        self.job_id = job_id
        self.label = label
        self.running = True
        self.phase = "starting"
        self.current = 0
        self.total = 0
        self.percent = 0
        self.message = ""
        self.detail = ""
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self.stop_event = threading.Event()
        self._last_write = 0.0
        self._write_interval = 1.0  # Write throttle (seconds)
        self._completion_data: dict = {}  # Extra data written on complete()

    @property
    def cancelled(self) -> bool:
        return self.stop_event.is_set()

    def cancel(self):
        self.stop_event.set()

    def update(self, phase: str = "", message: str = ""):
        if phase:
            self.phase = phase
        if message:
            self.message = message
        self._write_progress()

    def progress(self, current: int, total: int, detail: str = ""):
        self.current = current
        self.total = total
        self.percent = int((current / total) * 100) if total > 0 else 0
        self.detail = detail
        self._write_progress(throttled=True)

    def complete(self, message: str = ""):
        self.running = False
        self.phase = "complete"
        self.percent = 100
        if self.total > 0:
            self.current = self.total
        if message:
            self.message = message
        self.finished_at = time.time()
        self._write_progress()

    def complete_cancelled(self, message: str = ""):
        self.running = False
        self.phase = "cancelled"
        self.message = message or f"cancelled: {self.current} processed / {self.total} total"
        self.finished_at = time.time()
        self._write_progress()

    def fail(self, error: str):
        self.running = False
        self.phase = "error"
        self.error = error
        self.message = error
        self.finished_at = time.time()
        self._write_progress()

    def set_completion_data(self, **kwargs) -> None:
        """Store extra data to include in the final progress file."""
        self._completion_data.update(kwargs)

    def to_dict(self):
        elapsed = (self.finished_at or time.time()) - self.started_at
        d = {
            "job_id": self.job_id,
            "label": self.label,
            "running": self.running,
            "phase": self.phase,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "message": self.message,
            "detail": self.detail,
            "error": self.error,
            "elapsed_seconds": round(elapsed, 1),
        }
        if self._completion_data:
            d.update(self._completion_data)
        return d

    def _write_progress(self, throttled: bool = False):
        now = time.time()
        if throttled and (now - self._last_write) < self._write_interval:
            return
        self._last_write = now
        write_progress(self.to_dict())


# -- Signal / Parent monitoring -----------------------------------------------

def setup_signal_handler(job: FileBasedJob):
    """Set up SIGTERM/SIGINT for graceful shutdown."""
    install_cancel_signal_handlers(
        job.cancel,
        logger=logger,
        message="cancelling scan...",
    )


def start_parent_monitor(job: FileBasedJob, parent_pid: int):
    """Monitor parent process liveness (daemon thread)."""
    _start_parent_monitor(
        parent_pid=parent_pid,
        is_running=lambda: job.running,
        is_process_alive=is_process_alive,
        cancel=job.cancel,
        logger=logger,
        message="Parent PID %d is gone, cancelling scan...",
        interval=_PARENT_CHECK_INTERVAL,
    )


def run_scan_with_lifecycle(job: FileBasedJob, **kwargs):
    """Invoke run_scan_background and manage FileBasedJob lifecycle.

    run_scan_background() does not call complete/fail on external jobs,
    so this wrapper handles termination.
    """
    from core.scan.runtime import run_scan_background

    try:
        run_scan_background(job=job, **kwargs)
    except Exception as e:
        if job.running:
            job.fail(str(e))
        return

    # run_scan_background does not call complete/fail on external jobs
    if job.running:
        if job.cancelled:
            job.complete_cancelled()
        else:
            job.complete(job.message or "complete")
