"""SSE + webhook blueprint compatibility wrapper."""

from importlib import import_module

from core.sse.sse_routes import bp as sse_bp

webhooks_bp = import_module(
    "extensions.builtin_webhook.core_impl.webhook_routes"
).bp
webhooks_inbound_bp = import_module(
    "extensions.builtin_webhook.core_impl.webhook_inbound"
).bp

__all__ = ["sse_bp", "webhooks_bp", "webhooks_inbound_bp"]

