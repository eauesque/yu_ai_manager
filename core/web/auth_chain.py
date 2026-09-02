"""Authentication chain facade."""

from core.web.auth_chain_checks import (
    AuthResult,
    check_api_key,
    check_cookie,
    check_loopback_status_bypass,
    check_pin_bypass,
    check_quick_lock,
    check_session,
    check_share_bypass,
    check_static_bypass,
    check_trusted_peer,
    check_trusted_proxy,
)
from core.web.auth_chain_runner import run_chain

__all__ = [
    "AuthResult",
    "check_api_key",
    "check_cookie",
    "check_loopback_status_bypass",
    "check_pin_bypass",
    "check_quick_lock",
    "check_session",
    "check_share_bypass",
    "check_static_bypass",
    "check_trusted_peer",
    "check_trusted_proxy",
    "run_chain",
]
