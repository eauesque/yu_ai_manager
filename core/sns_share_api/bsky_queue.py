"""Bluesky notification queue and monitor config routes."""

import logging
from importlib import import_module

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync

# Extension directory contains a hyphen, so use importlib for the import
_SNS_BSKY_MON = "extensions.builtin_sns_share.core_impl.bsky_monitor"
_SNS_BSKY_CFG = "extensions.builtin_sns_share.core_impl.bsky_monitor_config"


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

logger = logging.getLogger(__name__)


async def bsky_queue():
    """Get Bluesky notification queue items.

    Query params: status, type, limit
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _mon = import_module(_SNS_BSKY_MON)
    status = request.args.get("status", "")
    ntype = request.args.get("type", "")
    limit = min(int(request.args.get("limit", "50")), 200)
    items = await run_db_sync(_mon.get_queue_items, status, ntype, limit)
    stats = await run_db_sync(_mon.get_queue_stats)
    return api_result({"data": {"items": items, "stats": stats}})


async def bsky_pending():
    """Get pending Bluesky notifications for MCP notification."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _mon = import_module(_SNS_BSKY_MON)
    items = await run_db_sync(_mon.get_pending_notifications)
    stats = await run_db_sync(_mon.get_queue_stats)
    return api_result({"data": {"items": items, "count": len(items), "stats": stats}})


async def bsky_triage(queue_id: int):
    """Set triage result for a queue item.

    Body: {"result": "valid" | "invalid"}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    body = await request.get_json(silent=True) or {}
    result = str(body.get("result", "")).strip()
    if result not in ("valid", "invalid"):
        return api_error("result must be 'valid' or 'invalid'", 400)
    _mon = import_module(_SNS_BSKY_MON)
    ok = await run_db_sync(_mon.update_triage_result, queue_id, result)
    if not ok:
        return api_error("Queue item not found", 404)
    try:
        from core.event_bus import emit
        emit("bsky_queue.triage_complete", {
            "queue_id": queue_id, "result": result,
        }, source="bsky_monitor")
    except Exception:
        logger.warning("step failed", exc_info=True)
    return api_result({"ok": True, "result": result})


async def bsky_status(queue_id: int):
    """Update queue item status.

    Body: {"status": "pending" | "notified" | "dismissed"}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    body = await request.get_json(silent=True) or {}
    status = str(body.get("status", "")).strip()
    if status not in ("pending", "notified", "dismissed"):
        return api_error("status must be pending, notified, or dismissed", 400)
    _mon = import_module(_SNS_BSKY_MON)
    ok = await run_db_sync(_mon.update_status, queue_id, status)
    if not ok:
        return api_error("Queue item not found", 404)
    return api_result({"ok": True})


async def bsky_respond(queue_id: int):
    """Send an auto-response reply to a notification.

    Body: {"text": "Response text"}
    Only works for mentions, replies, and quotes.
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    body = await request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    if not text:
        return api_error("text is required", 400)
    _mon = import_module(_SNS_BSKY_MON)
    ok = await run_db_sync(_mon.send_auto_response, queue_id, text)
    if not ok:
        return api_error("Failed to send response (item not found or not a mention/reply/quote)", 400)
    try:
        from core.event_bus import emit
        emit("bsky_queue.auto_responded", {
            "queue_id": queue_id,
        }, source="bsky_monitor")
    except Exception:
        logger.warning("step failed", exc_info=True)
    return api_result({"ok": True})


async def bsky_monitor_config_get():
    """Get Bluesky monitor configuration."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _cfg = import_module(_SNS_BSKY_CFG)
    cfg = await run_db_sync(_cfg.get_monitor_config)
    return api_result({"data": cfg})


async def bsky_monitor_config_save():
    """Update Bluesky monitor configuration.

    Body: {poll_interval_minutes?, auto_dismiss_follow?, auto_dismiss_like?,
           auto_dismiss_repost?, auto_respond_enabled?, notify_on_connect?}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    body = await request.get_json(silent=True) or {}
    _cfg = import_module(_SNS_BSKY_CFG)
    result = await run_db_sync(
        _cfg.save_monitor_config,
        poll_interval_minutes=body.get("poll_interval_minutes"),
        auto_dismiss_follow=body.get("auto_dismiss_follow"),
        auto_dismiss_like=body.get("auto_dismiss_like"),
        auto_dismiss_repost=body.get("auto_dismiss_repost"),
        auto_respond_enabled=body.get("auto_respond_enabled"),
        notify_on_connect=body.get("notify_on_connect"),
    )
    return api_result({"data": result})


async def bsky_triage_prompts_get():
    """Get Bluesky triage prompts + auto-response templates."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _cfg = import_module(_SNS_BSKY_CFG)
    prompts = await run_db_sync(_cfg.get_triage_prompts)
    responses = await run_db_sync(_cfg.get_auto_response_templates)
    return api_result({"data": {
        "triage_prompts": prompts,
        "auto_responses": responses,
        "triage_defaults": _cfg.TRIAGE_DEFAULTS,
        "auto_response_defaults": _cfg.AUTO_RESPONSE_DEFAULTS,
    }})


async def bsky_triage_prompts_save():
    """Update Bluesky triage prompts and/or auto-response templates.

    Body: {triage_prompts?: {mention?, reply?, quote?},
           auto_responses?: {mention?, reply?, quote?}}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    body = await request.get_json(silent=True) or {}
    result = {}
    tp = body.get("triage_prompts")
    if tp and isinstance(tp, dict):
        _cfg = import_module(_SNS_BSKY_CFG)
        result["triage_prompts"] = await run_db_sync(
            _cfg.save_triage_prompts,
            mention=tp.get("mention"),
            reply=tp.get("reply"),
            quote=tp.get("quote"),
        )
    ar = body.get("auto_responses")
    if ar and isinstance(ar, dict):
        _cfg = import_module(_SNS_BSKY_CFG)
        result["auto_responses"] = await run_db_sync(
            _cfg.save_auto_response_templates,
            mention=ar.get("mention"),
            reply=ar.get("reply"),
            quote=ar.get("quote"),
        )
    return api_result({"data": result})


async def bsky_poll():
    """Trigger immediate Bluesky notification polling."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        from core.scheduler_core import scheduler_manager
        if scheduler_manager.is_running:
            scheduler_manager.trigger_job("bsky_notification_poll")
            return api_result({"ok": True, "message": "Poll triggered"})
        else:
            _mon = import_module(_SNS_BSKY_MON)
            counts = await run_db_sync(_mon.poll_notifications)
            total = sum(counts.values())
            return api_result({"ok": True, "message": f"{total} new notifications", "counts": counts})
    except Exception as e:
        return api_error(f"Poll failed: {e}", 500)
