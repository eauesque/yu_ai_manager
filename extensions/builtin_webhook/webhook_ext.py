"""builtin-webhook Extension entrypoint.

Routes are registered via core_shim → core.webhook.webhook_routes
and core.webhook.webhook_inbound (see routes/events.py).
"""
from quart import Blueprint


def get_blueprint() -> Blueprint:
    return Blueprint("webhook", __name__)


__all__ = ["get_blueprint"]
