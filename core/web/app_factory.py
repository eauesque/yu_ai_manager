"""Quart app factory helpers (compatibility facade)."""

from core.web.app_factory_blueprints import register_blueprints
from core.web.error_handlers import register_error_handlers
from core.web.request_hooks import register_request_hooks as register_request_debug_hooks

__all__ = [
    "register_blueprints",
    "register_request_debug_hooks",
    "register_error_handlers",
]
