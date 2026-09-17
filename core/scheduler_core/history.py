"""Execution history ring buffer for scheduled jobs."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class ExecutionRecord:
    """Single job execution result."""

    __slots__ = ("job_id", "timestamp", "duration_ms", "success", "error", "result_summary")

    def __init__(
        self,
        job_id: str,
        timestamp: float,
        duration_ms: int,
        success: bool,
        error: str | None = None,
        result_summary: str | None = None,
    ):
        self.job_id = job_id
        self.timestamp = timestamp
        self.duration_ms = duration_ms
        self.success = success
        self.error = error
        self.result_summary = result_summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "result_summary": self.result_summary,
        }


class ExecutionHistory:
    """Thread-safe ring buffer for job execution history."""

    def __init__(self, max_size: int = 100):
        self._buffer: deque[ExecutionRecord] = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def record(
        self,
        job_id: str,
        duration_ms: int,
        success: bool,
        error: str | None = None,
        result_summary: str | None = None,
    ) -> ExecutionRecord:
        rec = ExecutionRecord(
            job_id=job_id,
            timestamp=time.time(),
            duration_ms=duration_ms,
            success=success,
            error=error,
            result_summary=result_summary,
        )
        with self._lock:
            self._buffer.append(rec)
        return rec

    def get_all(self) -> list[dict[str, Any]]:
        """Return all records newest-first."""
        with self._lock:
            return [r.to_dict() for r in reversed(self._buffer)]

    def get_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """Return records for a specific job, newest-first."""
        with self._lock:
            return [
                r.to_dict() for r in reversed(self._buffer)
                if r.job_id == job_id
            ]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
