"""Auth/lock compatibility facade."""

from core.web.auth_lock_state import (
    QuickLock,
    RateLimiter,
    approval_pin_source,
    hash_pin,
    is_approval_pin_expired,
    make_token,
    quick_lock,
    rate_limiter,
    verify_approval_pin,
)
from core.web.auth_restart import (
    has_remote_restart_token,
    is_local_request,
    is_remote_restart_authorized,
    is_truthy_env,
    restart_state,
)

__all__ = [
    "QuickLock",
    "RateLimiter",
    "approval_pin_source",
    "has_remote_restart_token",
    "hash_pin",
    "is_approval_pin_expired",
    "is_local_request",
    "is_remote_restart_authorized",
    "is_truthy_env",
    "make_token",
    "quick_lock",
    "rate_limiter",
    "restart_state",
    "verify_approval_pin",
]
