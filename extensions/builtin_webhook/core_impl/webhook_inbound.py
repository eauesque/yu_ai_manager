"""Inbound webhook receive endpoint."""

from __future__ import annotations

import hashlib
import hmac
import logging

from quart import Blueprint, request

from core.event_bus import emit
from core.event_bus.event_types import WEBHOOK_RECEIVED

from .webhook_inbound_config import get_inbound_by_token

bp = Blueprint("webhooks_inbound", __name__)
logger = logging.getLogger(__name__)


@bp.route("/api/webhooks/receive/<token>", methods=["POST"])
async def api_receive_webhook(token: str):
    """Receive an external webhook trigger. Token-authenticated, no PIN session required."""
    wh = get_inbound_by_token(token)
    if wh is None:
        return {"error": "Invalid or inactive token"}, 403

    body = await request.get_data()

    # Optional HMAC verification
    sig_header = request.headers.get("X-Webhook-Signature", "")
    if sig_header:
        from .webhook_config import get_secret
        secret = get_secret()
        expected = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            logger.warning("Inbound webhook %s: HMAC mismatch", wh["id"])
            return {"error": "Invalid signature"}, 403

    # Parse JSON payload
    try:
        data = await request.get_json(silent=True)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    # Determine event type
    event_type = data.get("event", "")
    event_data = data.get("data", {})

    if event_type:
        allowed = wh.get("allowed_events", [])
        if allowed and event_type not in allowed:
            return {"error": f"Event '{event_type}' not in allowed_events"}, 403
        emit(event_type, {
            "source_webhook": wh["id"],
            "original_data": event_data,
        }, source="inbound_webhook")
    else:
        event_type = WEBHOOK_RECEIVED
        emit(WEBHOOK_RECEIVED, {
            "source_webhook": wh["id"],
            "payload": data,
        }, source="inbound_webhook")

    logger.info("Inbound webhook %s: emitted %s", wh["id"], event_type)
    return {"ok": True, "event": event_type}, 200
