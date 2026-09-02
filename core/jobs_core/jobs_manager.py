"""Thread-safe background job manager."""

import threading
import time
from typing import Any

from .jobs_model import Job


class JobManager:
    HISTORY_TTL = 60

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    def start(self, job_id: str, label: str) -> Job:
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing and existing.running:
                raise ValueError(f"Job '{job_id}' is already running")
            job = Job(job_id, label)
            self._jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def get_raw_job(self, job_id: str) -> Job | None:
        """Return the Job object directly (for bridge use)."""
        with self._lock:
            return self._jobs.get(job_id)

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.running if job else False

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.running:
                job.cancel()
                return True
            return False

    def get_status(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            expired = [
                k
                for k, v in self._jobs.items()
                if not v.running and v.finished_at and (now - v.finished_at) > self.HISTORY_TTL
            ]
            for k in expired:
                del self._jobs[k]

            active = []
            recent = []
            for job in self._jobs.values():
                d = job.to_dict()
                if job.running:
                    active.append(d)
                else:
                    recent.append(d)

        return {
            "has_active": len(active) > 0,
            "active": active,
            "recent": recent,
        }

    def get_legacy_scan_state(self) -> dict[str, Any]:
        with self._lock:
            running_jobs = [j for j in self._jobs.values() if j.running]
            if not running_jobs:
                recent = [j for j in self._jobs.values() if not j.running]
                if recent:
                    latest = max(recent, key=lambda j: j.finished_at or 0)
                    d = latest.to_dict()
                    return _legacy_payload(False, d)
                return {
                    "running": False,
                    "phase": "idle",
                    "current": 0,
                    "total": 0,
                    "percent": 0,
                    "current_file": "",
                    "message": "",
                    "error": None,
                    "job_id": None,
                    "label": None,
                }

            job = next((j for j in running_jobs if j.job_id == "scan"), running_jobs[0])
            return _legacy_payload(True, job.to_dict())


def _legacy_payload(running: bool, d: dict[str, Any]) -> dict[str, Any]:
    return {
        "running": running,
        "phase": d["phase"],
        "current": d["current"],
        "total": d["total"],
        "percent": d["percent"],
        "current_file": d["detail"],
        "message": d["message"],
        "error": d["error"],
        "job_id": d["job_id"],
        "label": d["label"],
    }
