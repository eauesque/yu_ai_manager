"""REST API for the task scheduler."""

import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_result

bp = Blueprint("scheduler", __name__)
logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _mgr():
    from core.scheduler_core import scheduler_manager
    return scheduler_manager


# -- Status & listing (read-only, no rate limit) --------------------------

@bp.route("/api/scheduler/status")
async def scheduler_status():
    """Return scheduler status and all jobs."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result({"status": _mgr().get_status()}, 200)


@bp.route("/api/scheduler/jobs")
async def scheduler_jobs():
    """List all scheduled jobs."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result({"jobs": _mgr().list_jobs()}, 200)


@bp.route("/api/scheduler/history")
async def scheduler_history():
    """Return execution history (newest first, max 100)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result({"history": _mgr().history.get_all()}, 200)


# -- Job management (write) -----------------------------------------------

@bp.route("/api/scheduler/jobs", methods=["POST"])
async def scheduler_add_job():
    """Add a custom job."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()
    func_name = data.get("func_name", "").strip()
    trigger_type = data.get("trigger", "cron")
    trigger_args = data.get("trigger_args", {})

    if not job_id or not func_name:
        return api_result({"error": "job_id and func_name are required"}, 400)

    try:
        job = _mgr().add_job(job_id, func_name, trigger_type, **trigger_args)
        return api_result({"job": job}, 201)
    except (ValueError, RuntimeError) as e:
        logger.warning("Scheduler add job failed: %s", e)
        return api_result({"error": "Invalid scheduler job request"}, 400)


@bp.route("/api/scheduler/jobs/<job_id>", methods=["DELETE"])
async def scheduler_remove_job(job_id):
    """Remove a job."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        _mgr().remove_job(job_id)
        return api_result({"removed": job_id}, 200)
    except Exception as e:
        logger.warning("Scheduler remove job failed for %s: %s", job_id, e)
        return api_result({"error": "Job not found"}, 404)


# -- Pause / Resume / Trigger (write) -------------------------------------

@bp.route("/api/scheduler/jobs/<job_id>/pause", methods=["POST"])
async def scheduler_pause_job(job_id):
    """Pause a job."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        job = _mgr().pause_job(job_id)
        return api_result({"job": job}, 200)
    except KeyError as e:
        logger.warning("Scheduler pause job not found for %s: %s", job_id, e)
        return api_result({"error": "Job not found"}, 404)
    except RuntimeError as e:
        logger.warning("Scheduler pause job failed for %s: %s", job_id, e)
        return api_result({"error": "Job cannot be paused"}, 400)


@bp.route("/api/scheduler/jobs/<job_id>/resume", methods=["POST"])
async def scheduler_resume_job(job_id):
    """Resume a paused job."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        job = _mgr().resume_job(job_id)
        return api_result({"job": job}, 200)
    except KeyError as e:
        logger.warning("Scheduler resume job not found for %s: %s", job_id, e)
        return api_result({"error": "Job not found"}, 404)
    except RuntimeError as e:
        logger.warning("Scheduler resume job failed for %s: %s", job_id, e)
        return api_result({"error": "Job cannot be resumed"}, 400)


@bp.route("/api/scheduler/jobs/<job_id>/trigger", methods=["POST"])
async def scheduler_trigger_job(job_id):
    """Trigger immediate execution of a job."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        _mgr().trigger_job(job_id)
        return api_result({"triggered": job_id}, 200)
    except KeyError as e:
        logger.warning("Scheduler trigger job not found for %s: %s", job_id, e)
        return api_result({"error": "Job not found"}, 404)
    except RuntimeError as e:
        logger.warning("Scheduler trigger job failed for %s: %s", job_id, e)
        return api_result({"error": "Job cannot be triggered"}, 400)
