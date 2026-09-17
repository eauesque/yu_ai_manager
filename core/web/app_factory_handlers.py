"""Compatibility facade for Quart app-factory hook registration.

Internal code should prefer ``error_handlers`` and ``request_hooks`` directly
when practical. This file remains for compatibility.
"""

from core.web.error_handlers import register_error_handlers
from core.web.request_hooks import register_request_hooks as register_request_debug_hooks

__all__ = [
    "register_error_handlers",
    "register_request_debug_hooks",
]
