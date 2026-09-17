"""SchedulerManager: APScheduler BackgroundScheduler wrapper.

Provides a singleton interface for managing scheduled jobs with
cron/interval/date triggers. Jobs are defined in config.json and
can also be added/removed at runtime via the REST API.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .builtin_jobs import BUILTIN_JOBS
from .history import ExecutionHistory

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages APScheduler lifecycle and job operations."""

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler | None = None
        self._history = ExecutionHistory(max_size=100)
        self._running = False

    # -- Lifecycle ---------------------------------------------------------

    def start(self, config: dict) -> None:
        """Initialize and start the scheduler from config."""
        if self._running:
            logger.warning("[SCHEDULER] Already running, skip start")
            return

        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            },
        )

        # Listen for job execution events
        self._scheduler.add_listener(
            self._on_job_executed, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        # Register built-in jobs from config
        jobs_cfg = config.get("jobs", {})
        for job_id, job_conf in jobs_cfg.items():
            if not job_conf.get("enabled", True):
                continue
            func = BUILTIN_JOBS.get(job_id)
            if func is None:
                logger.warning("[SCHEDULER] Unknown built-in job: %s", job_id)
                continue
            trigger = self._build_trigger(job_conf)
            if trigger is None:
                logger.warning("[SCHEDULER] Invalid trigger for job: %s", job_id)
                continue
            self._scheduler.add_job(
                func, trigger=trigger, id=job_id, replace_existing=True,
            )
            logger.info("  [SCHEDULER] Registered job: %s", job_id)

        self._scheduler.start()
        self._running = True

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("[SCHEDULER] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # -- Job operations ----------------------------------------------------

    def add_job(
        self,
        job_id: str,
        func_name: str,
        trigger_type: str,
        **trigger_args: Any,
    ) -> dict[str, Any]:
        """Add a new job (must be a builtin job function)."""
        self._ensure_running()
        func = BUILTIN_JOBS.get(func_name)
        if func is None:
            raise ValueError(f"Unknown job function: {func_name}")

        trigger = self._build_trigger({"trigger": trigger_type, **trigger_args})
        if trigger is None:
            raise ValueError(f"Invalid trigger type: {trigger_type}")

        self._scheduler.add_job(
            func, trigger=trigger, id=job_id, replace_existing=True,
        )
        return self._job_to_dict(self._scheduler.get_job(job_id))

    def remove_job(self, job_id: str) -> None:
        """Remove a job by ID."""
        self._ensure_running()
        self._scheduler.remove_job(job_id)

    def pause_job(self, job_id: str) -> dict[str, Any]:
        """Pause a job."""
        self._ensure_running()
        job = self._scheduler.get_job(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        self._scheduler.pause_job(job_id)
        return self._job_to_dict(self._scheduler.get_job(job_id))

    def resume_job(self, job_id: str) -> dict[str, Any]:
        """Resume a paused job."""
        self._ensure_running()
        job = self._scheduler.get_job(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        self._scheduler.resume_job(job_id)
        return self._job_to_dict(self._scheduler.get_job(job_id))

    def trigger_job(self, job_id: str) -> None:
        """Trigger immediate execution of a job via a one-shot date trigger."""
        self._ensure_running()
        job = self._scheduler.get_job(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        # Add a one-shot job that runs immediately; original schedule is untouched
        self._scheduler.add_job(
            job.func, trigger="date", id=f"_trigger_{job_id}",
            replace_existing=True,
        )

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return all registered jobs with metadata."""
        if not self._scheduler or not self._running:
            return []
        return [self._job_to_dict(j) for j in self._scheduler.get_jobs()]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get a single job by ID."""
        if not self._scheduler or not self._running:
            return None
        job = self._scheduler.get_job(job_id)
        if job is None:
            return None
        return self._job_to_dict(job)

    def get_status(self) -> dict[str, Any]:
        """Return scheduler status overview with last result per job."""
        jobs = self.list_jobs()
        # Attach last execution result to each job
        for job in jobs:
            last = self._history.get_for_job(job["id"])
            if last:
                r = last[0]
                job["last_success"] = r["success"]
                job["last_time"] = r["timestamp"]
                job["last_summary"] = r.get("result_summary") or r.get("error") or ""
        return {
            "running": self._running,
            "job_count": len(jobs),
            "jobs": jobs,
        }

    @property
    def history(self) -> ExecutionHistory:
        return self._history

    # -- Internal ----------------------------------------------------------

    def _ensure_running(self) -> None:
        if not self._scheduler or not self._running:
            raise RuntimeError("Scheduler is not running")

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Record execution result and emit SSE event."""
        job_id = event.job_id
        # Skip one-shot trigger jobs from history
        if job_id.startswith("_trigger_"):
            job_id = job_id[len("_trigger_"):]

        # APScheduler does not provide duration; record with 0.
        if event.exception:
            error_msg = str(event.exception)
            self._history.record(
                job_id=job_id, duration_ms=0,
                success=False, error=error_msg,
            )
            self._emit_sse("scheduler.job_error", {
                "job_id": job_id, "error": error_msg,
            })
        else:
            result_summary = str(event.retval) if event.retval else None
            self._history.record(
                job_id=job_id, duration_ms=0,
                success=True, result_summary=result_summary,
            )
            self._emit_sse("scheduler.job_executed", {
                "job_id": job_id, "result": result_summary,
            })

    @staticmethod
    def _emit_sse(event_type: str, data: dict) -> None:
        """Emit an SSE event via the global event bus."""
        try:
            from core.event_bus import emit
            emit(event_type, data, source="scheduler")
        except Exception:
            logger.warning("step failed", exc_info=True)

    @staticmethod
    def _build_trigger(conf: dict):
        """Build an APScheduler trigger from config dict."""
        trigger_type = conf.get("trigger", "cron")
        if trigger_type == "cron":
            kwargs = {}
            for key in ("year", "month", "day", "week", "day_of_week",
                        "hour", "minute", "second"):
                if key in conf:
                    kwargs[key] = conf[key]
            return CronTrigger(**kwargs)
        elif trigger_type == "interval":
            kwargs = {}
            for key in ("weeks", "days", "hours", "minutes", "seconds"):
                if key in conf:
                    kwargs[key] = conf[key]
            return IntervalTrigger(**kwargs)
        return None

    @staticmethod
    def _job_to_dict(job) -> dict[str, Any]:
        """Convert an APScheduler Job to a serializable dict."""
        next_run = None
        if job.next_run_time:
            next_run = job.next_run_time.isoformat()
        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": next_run,
            "paused": job.next_run_time is None and not job.id.startswith("_trigger_"),
            "trigger": str(job.trigger),
        }
