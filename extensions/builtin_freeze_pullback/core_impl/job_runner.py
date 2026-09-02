"""Rendering job management.

Uses JobManager and threading.Thread to generate video in the background.
Notifies progress via SSE events.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from core.event_bus import emit
from core.event_bus.event_types import (
    FPB_COMPLETE,
    FPB_ERROR,
    FPB_START,
)
from core.jobs_core.jobs_manager import JobManager

from .renderer import render_video
from .validation import RenderParams

logger = logging.getLogger(__name__)

JOB_ID = "freeze_pullback"

# Module-level job manager
_job_manager = JobManager()
_render_lock = threading.Lock()


def start_render_job(params: RenderParams, output_dir: str | None = None) -> dict[str, Any]:
    """Start a rendering job.

    Only one job can run at a time.

    Returns:
        {"status": "started", "job_id": "..."} or {"error": "..."}
    """
    if _job_manager.is_running(JOB_ID):
        return {"error": "A render job is already running", "job_id": JOB_ID}

    try:
        job = _job_manager.start(JOB_ID, label="Freeze & Pull-back")
    except ValueError:
        return {"error": "A render job is already running", "job_id": JOB_ID}

    emit(FPB_START, {"file_id": params.file_id}, source="fpb")

    def _run():
        try:
            result_path = render_video(params, job=job, output_dir=output_dir)
            if not result_path:
                # Cancelled
                job.complete_cancelled()
                return
            job.complete(message=f"Completed: {result_path}")
            emit(
                FPB_COMPLETE,
                {"file_id": params.file_id, "output": result_path},
                source="fpb",
            )
        except Exception as exc:
            logger.error("FPB render failed: %s", exc)
            job.fail(str(exc))
            emit(
                FPB_ERROR,
                {"file_id": params.file_id, "error": str(exc)},
                source="fpb",
            )

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {"status": "started", "job_id": JOB_ID}


def get_job_status() -> dict[str, Any]:
    """Return the current job status."""
    status = _job_manager.get_job(JOB_ID)
    if not status:
        return {
            "running": False,
            "phase": "idle",
            "current": 0,
            "total": 0,
            "percent": 0,
            "message": "",
            "error": None,
        }
    return status


def cancel_job() -> bool:
    """Cancel the running job."""
    return _job_manager.cancel_job(JOB_ID)


def get_active_job() -> dict[str, Any] | None:
    """Return the active job if one is running."""
    if _job_manager.is_running(JOB_ID):
        return _job_manager.get_job(JOB_ID)
    return None
