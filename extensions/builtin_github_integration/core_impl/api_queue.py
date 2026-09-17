"""Issue queue management API routes."""

from __future__ import annotations

import logging

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from ._blueprint import bp

logger = logging.getLogger(__name__)

# ── Issue Queue ─────────────────────────────────────────────────

@bp.route("/api/github/queue", methods=["GET"])
async def get_issue_queue():
    """Get issue queue items.

    Query params: status (pending/notified/dismissed), limit (default 50)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .issue_queue import get_queue_items, get_queue_stats
    status = request.args.get("status", "")
    try:
        limit = max(1, min(int(request.args.get("limit", "50")), 200))
    except (ValueError, TypeError):
        limit = 50
    items = await run_db_sync(get_queue_items, status, limit)
    stats = await run_db_sync(get_queue_stats)
    return api_result({"data": {"items": items, "stats": stats}})


@bp.route("/api/github/queue/pending", methods=["GET"])
async def get_pending_queue():
    """Get pending issues for MCP notification."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .issue_queue import get_pending_count, get_pending_issues
    items = await run_db_sync(get_pending_issues)
    count = await run_db_sync(get_pending_count)
    return api_result({"data": {"items": items, "count": count}})


@bp.route("/api/github/queue/<int:queue_id>/triage", methods=["POST"])
async def triage_queue_item(queue_id: int):
    """Set triage result for a queue item.

    Body: {"result": "valid" | "invalid"}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    result = str(data.get("result", "")).strip()
    if result not in ("valid", "invalid"):
        return api_error("result must be 'valid' or 'invalid'", 400)

    from core.services_core.github_issue_queue_service import update_triage_result
    ok = await run_db_sync(update_triage_result, queue_id, result)
    if not ok:
        return api_error("Queue item not found or invalid result", 404)

    # Emit SSE
    try:
        from core.event_bus import emit
        emit("github_queue.triage_complete", {
            "queue_id": queue_id, "result": result,
        }, source="github")
    except Exception:
        logger.warning("github queue event was not emitted", exc_info=True)

    return api_result({"ok": True, "result": result})


@bp.route("/api/github/queue/<int:queue_id>/dismiss", methods=["POST"])
async def dismiss_queue_item(queue_id: int):
    """Dismiss a queue item (auto-close if configured).

    Body: {"auto_close": bool, "account_label": str?}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    auto_close = data.get("auto_close", False)
    account_label = str(data.get("account_label", "")).strip()

    from core.services_core.github_issue_queue_service import dismiss_invalid

    from .issue_queue import get_queue_items

    # Get the queue item first
    all_items = await run_db_sync(get_queue_items, "", 500)
    item = next((i for i in all_items if i["id"] == queue_id), None)
    if not item:
        return api_error("Queue item not found", 404)

    closed = False
    if auto_close and account_label and item:
        from .account_store import get_account
        from .github_client import add_issue_comment, close_issue
        from .issue_queue import INVALID_ISSUE_COMMENT

        acc = await run_db_sync(get_account, account_label)
        if acc and acc.get("token"):
            # Post comment first, then close
            await run_db_sync(
                add_issue_comment,
                acc["token"], item["repo"], item["issue_number"],
                INVALID_ISSUE_COMMENT,
            )
            code, _ = await run_db_sync(
                close_issue,
                acc["token"], item["repo"], item["issue_number"],
            )
            closed = code == 200

    ok = await run_db_sync(dismiss_invalid, queue_id)
    if not ok:
        return api_error("Failed to dismiss", 500)

    try:
        from core.event_bus import emit
        emit("github_queue.dismissed", {
            "queue_id": queue_id,
            "auto_closed": closed,
            "repo": item["repo"] if item else "",
            "issue_number": item["issue_number"] if item else 0,
        }, source="github")
    except Exception:
        logger.warning("api_queue.py: step failed", exc_info=True)

    return api_result({"ok": True, "auto_closed": closed})


@bp.route("/api/github/queue/<int:queue_id>/status", methods=["PUT"])
async def update_queue_status(queue_id: int):
    """Update queue item status.

    Body: {"status": "pending" | "notified" | "dismissed"}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()
    if status not in ("pending", "notified", "dismissed"):
        return api_error("status must be pending, notified, or dismissed", 400)

    from core.services_core.github_issue_queue_service import update_status
    ok = await run_db_sync(update_status, queue_id, status)
    if not ok:
        return api_error("Queue item not found", 404)
    return api_result({"ok": True})


@bp.route("/api/github/queue/config", methods=["GET"])
async def get_queue_config():
    """Get issue queue configuration."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_queue_config as _get
    cfg = await run_db_sync(_get)
    return api_result({"data": cfg})


@bp.route("/api/github/queue/config", methods=["PUT"])
async def save_queue_config():
    """Update issue queue configuration.

    Body: {"poll_interval_minutes": int?, "auto_close_invalid": bool?,
           "notify_on_connect": bool?}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    from .account_store import save_queue_config as _save
    result = await run_db_sync(
        _save,
        poll_interval_minutes=data.get("poll_interval_minutes"),
        auto_close_invalid=data.get("auto_close_invalid"),
        notify_on_connect=data.get("notify_on_connect"),
    )
    return api_result({"data": result})


@bp.route("/api/github/queue/poll", methods=["POST"])
async def trigger_poll():
    """Trigger immediate issue polling for all accounts."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        from core.scheduler_core import scheduler_manager
        if scheduler_manager.is_running:
            scheduler_manager.trigger_job("github_issue_poll")
            return api_result({"ok": True, "message": "Poll triggered"})
        else:
            # Run poll directly if scheduler not running
            from core.scheduler_core.builtin_jobs import github_issue_poll
            result = await run_db_sync(github_issue_poll)
            return api_result({"ok": True, "message": str(result)})
    except Exception as e:
        return api_error(f"Poll failed: {e}", 500)
