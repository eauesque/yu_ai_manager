"""API payload builders for scan operations."""

import logging
import threading
from typing import Any

from core.event_bus import emit
from core.helpers_core.helpers_text_path import sanitize_user_path
from core.infra_core.api_validation import error_payload
from core.infra_core.debug_log import dlog
from core.scan.worker_ipc import is_worker_running, signal_stop
from core.scan_core.scan_state import clear_scan_state, load_scan_state

logger = logging.getLogger(__name__)


def start_scan_payload(data: dict[str, Any], remote_addr: str) -> tuple[dict[str, Any], int]:
    """Build response payload for starting a scan."""
    dlog("scan", "scan_start.request", payload=data, remote_addr=remote_addr)

    if not data or "root" not in data:
        dlog("scan", "scan_start.bad_request", reason="missing_root")
        return error_payload("root path required", "root_required", 400)

    root_path = sanitize_user_path(data["root"])
    recursive = data.get("recursive", True)
    force = data.get("force", False)
    scan_zips = data.get("scan_zips", False)

    from core.jobs_core.jobs import job_manager
    if job_manager.is_running("scan") or is_worker_running():
        # Already running -> add to queue
        from core.event_bus.event_types import SCAN_QUEUED
        from core.scan_core.scan_queue import scan_queue

        try:
            label = f"フォルダスキャン: {root_path}"
            item = scan_queue.enqueue(
                root=root_path, recursive=recursive,
                force=force, scan_zips=scan_zips,
                label=label, source="api",
            )
            emit(SCAN_QUEUED, {
                "queue_id": item.queue_id,
                "root": root_path,
                "label": label,
                "position": scan_queue.size(),
            }, source="scan_queue")
            dlog("scan", "scan_start.queued", root=root_path, queue_id=item.queue_id)
            return {
                "status": "queued",
                "queue_id": item.queue_id,
                "position": scan_queue.size(),
            }, 202
        except ValueError:
            logger.exception("Failed to enqueue scan request", extra={"root": root_path})
            return error_payload("Scan request could not be queued", "queue_error", 409)

    dlog("scan", "scan_start.paths", raw=data["root"], sanitized=root_path)

    # Clear stale interrupted state
    clear_scan_state()

    from core.scan_api.ops_worker import _start_worker_and_bridge
    _start_worker_and_bridge(root_path, recursive, force, scan_zips)
    dlog("scan", "scan_start.worker_spawned", root=root_path)
    return {"status": "started"}, 200


def scan_status_payload() -> dict[str, Any]:
    """Return scan status dict for /api/scan/status."""
    from core.jobs_core.jobs import job_manager
    return job_manager.get_legacy_scan_state()


# Backward-compat alias retained for existing test that monkey-patches by name.
legacy_scan_status_payload = scan_status_payload


def jobs_status_payload() -> dict[str, Any]:
    """Return all jobs status dict."""
    from core.jobs_core.jobs import job_manager
    return job_manager.get_status()


def cancel_scan_payload() -> tuple[dict[str, Any], int]:
    """Build response payload for cancelling a scan."""
    from core.jobs_core.jobs import job_manager

    # Send stop signal to worker process
    if is_worker_running():
        signal_stop()
        dlog("scan", "scan_cancel.signal_sent")
        return {"status": "cancelling", "message": "スキャン停止を要求しました"}, 200

    if job_manager.cancel_job("scan"):
        dlog("scan", "scan_cancel.accepted", target="scan")
        return {"status": "cancelling", "message": "スキャン停止を要求しました"}, 200
    if job_manager.cancel_job("scan-all"):
        dlog("scan", "scan_cancel.accepted", target="scan-all")
        return {"status": "cancelling", "message": "一括スキャン停止を要求しました"}, 200

    dlog("scan", "scan_cancel.rejected", reason="none_running")
    return error_payload("no running scan to cancel", "scan_not_running", 404)


def resume_scan_payload() -> tuple[dict[str, Any], int]:
    """Build response payload for resuming an interrupted scan."""
    state = load_scan_state()
    dlog("scan", "scan_resume.request", has_state=state is not None)
    if state is None:
        return error_payload("no interrupted scan", "no_interrupted_scan", 404)

    from core.jobs_core.jobs import job_manager
    if job_manager.is_running("scan") or is_worker_running():
        dlog("scan", "scan_resume.rejected", reason="already_running")
        return error_payload("scan already running", "scan_already_running", 409)

    root_path = state["root"]
    recursive = state.get("recursive", True)
    scan_zips = state.get("scan_zips", False)

    from core.scan_api.ops_worker import _start_worker_and_bridge
    _start_worker_and_bridge(root_path, recursive, False, scan_zips, resume=True)
    dlog("scan", "scan_resume.worker_spawned", root=root_path)
    return {"status": "resumed", "root": root_path}, 200


# -- Hash backfill operations -----------------------------------------------

def start_hash_backfill_payload() -> tuple[dict[str, Any], int]:
    """Start a hash backfill job."""
    from core.jobs_core.jobs import job_manager
    from core.scan.hash_backfill import run_hash_backfill

    if job_manager.is_running("hash-backfill"):
        dlog("scan", "hash_backfill_start.rejected", reason="already_running")
        return error_payload("hash backfill already running", "backfill_already_running", 409)

    try:
        job = job_manager.start("hash-backfill", "Hash Backfill")
    except ValueError:
        return error_payload("hash backfill already running", "backfill_already_running", 409)

    thread = threading.Thread(
        target=run_hash_backfill,
        kwargs={"job": job},
        daemon=True,
    )
    thread.start()
    dlog("scan", "hash_backfill_start.thread_started")
    return {"status": "started"}, 200


def cancel_hash_backfill_payload() -> tuple[dict[str, Any], int]:
    """Cancel a running hash backfill job."""
    from core.jobs_core.jobs import job_manager

    if job_manager.cancel_job("hash-backfill"):
        dlog("scan", "hash_backfill_cancel.accepted")
        return {"status": "cancelling", "message": "hash backfill 停止を要求しました"}, 200

    dlog("scan", "hash_backfill_cancel.rejected", reason="none_running")
    return error_payload("no running hash backfill", "backfill_not_running", 404)


def hash_backfill_status_payload() -> tuple[dict[str, Any], int]:
    """Return hash backfill progress."""
    from core.scan.hash_backfill import get_backfill_status
    return get_backfill_status(), 200
