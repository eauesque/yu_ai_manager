"""MCP authentication — internal token management and auth checks.

Handles localhost detection, internal token rotation, and
Bearer API Key verification for LAN access.
"""

import os
import threading
import time

from quart import request

from core.infra_core.api_errors import api_error
from core.web.auth_restart import is_loopback_request

# Internal token for MCP requests (generated at startup, not exposed externally)
# Token rotates periodically to limit exposure window
_INTERNAL_TOKEN = os.urandom(32).hex()
_token_created_at = time.time()
_TOKEN_MAX_AGE = 3600  # Rotate every 1 hour
# Lock guarding rotation. Today the function is only called from the asyncio
# event loop (single-threaded), but DB executor / background workers may call
# it in the future, and a torn read where ``_token_created_at`` updates before
# ``_INTERNAL_TOKEN`` would let a caller observe the new timestamp with the
# old token (or vice versa).
_token_lock = threading.Lock()


def get_internal_token() -> str:
    """Return current internal token, rotating if expired."""
    global _INTERNAL_TOKEN, _token_created_at
    with _token_lock:
        if time.time() - _token_created_at > _TOKEN_MAX_AGE:
            _INTERNAL_TOKEN = os.urandom(32).hex()
            _token_created_at = time.time()
        return _INTERNAL_TOKEN


def _is_localhost() -> bool:
    """Check whether the request originates from localhost."""
    return is_loopback_request()


def _check_mcp_auth():
    """Authenticate MCP endpoint access.

    localhost -> no auth required
    LAN IP   -> admin API Key required (Bearer token)

    Returns None on success, or an error Response on failure.
    """
    if _is_localhost():
        return None  # OK

    # Bearer token verification
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return api_error("Unauthorized: API key required for LAN access", 401)

    from core.web.apikey_auth.key_auth import authenticate_api_key, check_api_key_rate_limit
    key_info = authenticate_api_key()
    if not key_info:
        return api_error("Invalid API key", 401)

    from core.web.apikey_auth.key_scopes import key_has_scope
    if not key_has_scope(key_info, "admin"):
        return api_error("Insufficient scope: requires 'admin'", 403)

    allowed, remaining = check_api_key_rate_limit(key_info)
    if not allowed:
        return api_error("Rate limit exceeded", 429)

    return None  # OK
