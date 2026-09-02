"""Scan API -- start/stop/progress, resume interrupted scans, error queries."""
import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.scan_api import (
    cancel_hash_backfill_payload,
    cancel_scan_payload,
    dismiss_interrupted_scan_payload,
    hash_backfill_status_payload,
    interrupted_scan_payload,
    jobs_status_payload,
    resume_scan_payload,
    scan_status_payload,
    start_hash_backfill_payload,
    start_scan_payload,
)
from core.scan_api.errors_ops import (
    scan_errors_list_payload,
)
from core.services_core.db_async import run_db_sync

bp = Blueprint("scan", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/scan/start", methods=["POST"])
async def api_scan_start():
    """Start scan API."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    remote_addr = request.remote_addr
    payload, status = await run_db_sync(start_scan_payload, data, remote_addr)
    return api_result(payload, status)


@bp.route("/api/scan/status")
async def api_scan_status():
    """Get scan progress API (backward-compatible + job manager integration)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(scan_status_payload), 200)


@bp.route("/api/jobs/status")
async def api_jobs_status():
    """All background job statuses (for banner UI)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(jobs_status_payload), 200)


@bp.route("/api/scan/cancel", methods=["POST"])
async def api_scan_cancel():
    """Cancel scan API."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await run_db_sync(cancel_scan_payload)
    return api_result(payload, status)


@bp.route("/api/scan/interrupted")
async def api_scan_interrupted():
    """Get previously interrupted scan info."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(interrupted_scan_payload), 200)


@bp.route("/api/scan/resume", methods=["POST"])
async def api_scan_resume():
    """Resume interrupted scan (force=False)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await run_db_sync(resume_scan_payload)
    return api_result(payload, status)


@bp.route("/api/scan/dismiss", methods=["POST"])
async def api_scan_dismiss():
    """Dismiss interrupted scan state."""
    return api_result(await run_db_sync(dismiss_interrupted_scan_payload), 200)


# -- Scan queue endpoints ------------------------------------------------

@bp.route("/api/scan/queue")
async def api_scan_queue_list():
    """List scan queue items."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.scan_core.scan_queue import scan_queue
    return api_result({"items": scan_queue.list_items(), "count": scan_queue.size()}, 200)


@bp.route("/api/scan/queue/<queue_id>", methods=["DELETE"])
async def api_scan_queue_remove(queue_id: str):
    """Remove individual item from the queue."""
    from core.scan_core.scan_queue import scan_queue
    if scan_queue.remove(queue_id):
        return api_result({"status": "removed"}, 200)
    from core.infra_core.api_validation import error_payload
    return api_result(error_payload("item not found", "not_found", 404)[0], 404)


@bp.route("/api/scan/queue/clear", methods=["POST"])
async def api_scan_queue_clear():
    """Clear all items from the queue."""
    from core.event_bus import emit
    from core.event_bus.event_types import SCAN_QUEUE_CLEARED
    from core.scan_core.scan_queue import scan_queue
    count = scan_queue.clear()
    emit(SCAN_QUEUE_CLEARED, {"cleared": count}, source="scan_queue")
    return api_result({"status": "cleared", "cleared": count}, 200)


# -- Scan error endpoints ------------------------------------------------

@bp.route("/api/scan-errors")
async def api_scan_errors_list():
    """List scan errors (encoding/timeout/FS)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    error_type = request.args.get("error_type", "")
    resolved = request.args.get("resolved", "")
    limit = int(request.args.get("limit", 200))

    def _fetch():
        from core.services_core.db_api import get_readonly_db
        con = get_readonly_db()
        return scan_errors_list_payload(
            con, error_type=error_type, resolved=resolved, limit=limit,
        )

    payload, status = await run_db_sync(_fetch)
    return api_result(payload, status)


@bp.route("/api/scan-errors/<int:error_id>/resolve", methods=["POST"])
async def api_scan_errors_resolve(error_id: int):
    """Mark a scan error as resolved."""
    from core.services_core.scan_errors_service import resolve_scan_error_entry

    payload, status = await run_db_sync(resolve_scan_error_entry, error_id)
    return api_result(payload, status)


@bp.route("/api/scan-errors/clear", methods=["POST"])
async def api_scan_errors_clear():
    """Bulk-delete resolved scan errors."""
    from core.services_core.scan_errors_service import clear_resolved_scan_errors

    payload, status = await run_db_sync(clear_resolved_scan_errors)
    return api_result(payload, status)


# -- Hash backfill endpoints ------------------------------------------------

@bp.route("/api/scan/history")
async def api_scan_history():
    """Return persistent scan history (newest first)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    limit = int(request.args.get("limit", 50))
    from core.scan_core.scan_history import get_history
    return api_result({"entries": get_history(limit), "limit": limit}, 200)


@bp.route("/api/scan/history/clear", methods=["POST"])
async def api_scan_history_clear():
    """Clear all scan history entries."""
    from core.scan_core import scan_history as _sh
    with _sh._lock:
        _sh._entries.clear()
        _sh._save()
    return api_result({"status": "cleared"}, 200)


@bp.route("/api/hash-backfill/start", methods=["POST"])
async def api_hash_backfill_start():
    """Start hash backfill job."""
    payload, status = await run_db_sync(start_hash_backfill_payload)
    return api_result(payload, status)


@bp.route("/api/hash-backfill/cancel", methods=["POST"])
async def api_hash_backfill_cancel():
    """Cancel hash backfill job."""
    payload, status = await run_db_sync(cancel_hash_backfill_payload)
    return api_result(payload, status)


@bp.route("/api/hash-backfill/status")
async def api_hash_backfill_status():
    """Query hash backfill progress."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await run_db_sync(hash_backfill_status_payload)
    return api_result(payload, status)


@bp.route("/_internal/scan/queue/consume", methods=["POST"])
async def api_internal_scan_queue_consume():
    """Rust bridge からの内部 API。loopback 限定。"""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return {"ok": False, "error": "forbidden"}, 403
    try:
        from core.scan_core.scan_queue_consumer import consume_next_queued_scan

        consume_next_queued_scan()
        return {"ok": True}
    except Exception as e:
        logging.getLogger(__name__).error("internal queue consume error: %s", e)
        return {"ok": False, "error": str(e)}, 500


@bp.route("/_internal/bridge/import-paths", methods=["POST"])
async def api_internal_bridge_import_paths():
    """Rust bridge からの保存画像 import API。loopback 限定。"""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return {"ok": False, "error": "forbidden"}, 403
    try:
        body = await request.get_json(silent=True)
        paths = body.get("paths") if isinstance(body, dict) else None
        if not isinstance(paths, list):
            return {"ok": False, "error": "paths_required"}, 400

        from core.bridge_core.bridge_import import import_saved_files_sync

        mapping = import_saved_files_sync([str(p) for p in paths])
        return {"ok": True, "mapping": mapping}
    except Exception as e:
        logging.getLogger(__name__).error("internal bridge import error: %s", e)
        return {"ok": False, "error": str(e)}, 500
