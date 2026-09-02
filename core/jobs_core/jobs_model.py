"""Job state model."""

import threading
import time
from typing import Any


class Job:
    def __init__(self, job_id: str, label: str):
        self.job_id = job_id
        self.label = label
        self.running = True
        self.phase = "starting"
        self.current = 0
        self.total = 0
        self.percent = 0
        self.message = ""
        self.detail = ""
        self.error: str | None = None
        self.result: Any = None  # arbitrary result payload for completed jobs
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.stop_event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self.stop_event.is_set()

    def cancel(self):
        self.stop_event.set()

    def complete_cancelled(self, message: str = ""):
        self.running = False
        self.phase = "cancelled"
        self.message = message or f"中断: {self.current}件処理済み / {self.total}件中"
        self.finished_at = time.time()

    def update(self, phase: str = "", message: str = ""):
        if phase:
            self.phase = phase
        if message:
            self.message = message

    def progress(self, current: int, total: int, detail: str = ""):
        self.current = current
        self.total = total
        self.percent = int((current / total) * 100) if total > 0 else 0
        self.detail = detail

    def complete(self, message: str = ""):
        self.running = False
        self.phase = "complete"
        self.percent = 100
        if self.total > 0:
            self.current = self.total
        if message:
            self.message = message
        self.finished_at = time.time()

    def fail(self, error: str):
        self.running = False
        self.phase = "error"
        self.error = error
        self.message = error
        self.finished_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        elapsed = (self.finished_at or time.time()) - self.started_at
        d: dict[str, Any] = {
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
        if self.result is not None:
            d["result"] = self.result
        return d
