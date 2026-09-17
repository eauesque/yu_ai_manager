"""Webhook management endpoints (PIN session required)."""

from __future__ import annotations

import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

from .webhook_config import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    update_webhook,
)
from .webhook_delivery_log import list_deliveries
from .webhook_dispatcher import WebhookDispatcher

bp = Blueprint("webhooks_core", __name__)
logger = logging.getLogger(__name__)

# Injected at registration time via init_webhook_routes()
_dispatcher: WebhookDispatcher | None = None


from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local


def init_webhook_routes(dispatcher: WebhookDispatcher) -> None:
    global _dispatcher
    _dispatcher = dispatcher


@bp.route("/_internal/webhooks-changed", methods=["POST"])
async def _internal_webhooks_changed():
    """Internal notify endpoint called by Rust after webhook config mutations."""
    err = _require_local("webhooks-changed notify")
    if err:
        return err
    from .webhook_config import _invalidate_webhook_cache
    from .webhook_inbound_config import _invalidate_inbound_cache

    _invalidate_webhook_cache()
    _invalidate_inbound_cache()
    return api_success({"ok": True})


@bp.route("/api/webhooks", methods=["POST"])
async def api_create_webhook():
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0]["error"], err[1])
    url = data.get("url", "").strip()
    if not url:
        return api_error("url is required", 400)
    events = data.get("events", [])
    if not isinstance(events, list):
        return api_error("events must be a list", 400)
    label = str(data.get("label", ""))[:128]
    events = [str(e)[:64] for e in events[:50]]
    try:
        result = create_webhook(url=url, events=events, label=label)
    except ValueError:
        logger.exception("Failed to create webhook")
        return api_error("Invalid webhook configuration", 400)
    return api_success(result, 201)


@bp.route("/api/webhooks", methods=["GET"])
async def api_list_webhooks():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    hooks = list_webhooks()
    return api_success({"webhooks": hooks})


@bp.route("/api/webhooks/<wh_id>", methods=["PUT"])
async def api_update_webhook(wh_id: str):
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0]["error"], err[1])
    try:
        result = update_webhook(wh_id, data)
    except ValueError:
        logger.exception("Failed to update webhook", extra={"webhook_id": wh_id})
        return api_error("Invalid webhook update", 400)
    if result is None:
        return api_error("Webhook not found", 404)
    return api_success(result)


@bp.route("/api/webhooks/<wh_id>", methods=["DELETE"])
async def api_delete_webhook(wh_id: str):
    if delete_webhook(wh_id):
        return api_success({"deleted": wh_id})
    return api_error("Webhook not found", 404)


@bp.route("/api/webhooks/<wh_id>/test", methods=["POST"])
async def api_test_webhook(wh_id: str):
    wh = get_webhook(wh_id)
    if wh is None:
        return api_error("Webhook not found", 404)
    if _dispatcher is None:
        return api_error("Webhook dispatcher not initialized", 500)
    result = await _dispatcher.send_test(wh)
    return api_success(result)


@bp.route("/api/webhooks/deliveries", methods=["GET"])
async def api_list_deliveries():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    webhook_id = request.args.get("webhook_id")
    limit = request.args.get("limit", "50")
    try:
        limit_int = min(int(limit), 500)
    except ValueError:
        limit_int = 50
    deliveries = list_deliveries(webhook_id=webhook_id, limit=limit_int)
    return api_success({"deliveries": deliveries})


# -- Inbound webhook CRUD (PIN session required) --

from .webhook_inbound_config import (
    create_inbound_webhook,
    delete_inbound_webhook,
    list_inbound_webhooks_redacted,
    update_inbound_webhook,
)


@bp.route("/api/webhooks/inbound", methods=["POST"])
async def api_create_inbound_webhook():
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0]["error"], err[1])
    label = str(data.get("label", ""))[:128]
    allowed_events = data.get("allowed_events", [])
    if not isinstance(allowed_events, list):
        return api_error("allowed_events must be a list", 400)
    allowed_events = [str(e)[:64] for e in allowed_events[:50]]
    result = create_inbound_webhook(label=label, allowed_events=allowed_events)
    return api_success(result, 201)


@bp.route("/api/webhooks/inbound", methods=["GET"])
async def api_list_inbound_webhooks():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    hooks = list_inbound_webhooks_redacted()
    return api_success({"inbound_webhooks": hooks})


@bp.route("/api/webhooks/inbound/<wh_id>", methods=["PUT"])
async def api_update_inbound_webhook(wh_id: str):
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0]["error"], err[1])
    result = update_inbound_webhook(wh_id, data)
    if result is None:
        return api_error("Inbound webhook not found", 404)
    return api_success(result)


@bp.route("/api/webhooks/inbound/<wh_id>", methods=["DELETE"])
async def api_delete_inbound_webhook(wh_id: str):
    if delete_inbound_webhook(wh_id):
        return api_success({"deleted": wh_id})
    return api_error("Inbound webhook not found", 404)
