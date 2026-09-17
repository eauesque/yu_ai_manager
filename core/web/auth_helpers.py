"""Shared route auth helpers.

Reusable scope/auth gates that were previously copy-pasted into ~90 route
files. Each function returns either ``None`` (auth passed) or a Quart
response tuple suitable for an early ``return`` in a handler.

Usage::

    from core.web.auth_helpers import require_admin_scope

    @bp.route("/api/foo")
    async def api_foo():
        if (err := require_admin_scope()):
            return err
        ...
"""

from __future__ import annotations

from typing import Any

from quart import current_app, request, session

from core.infra_core.api_errors import api_error
from core.web.apikey_auth.key_scopes import key_has_scope


async def check_mutation_auth(request) -> tuple[Any, int] | None:
    """Returns (error_response, status) if unauthorized, None if allowed.

    Uses allow_loopback_bypass=False so loopback requests also need
    GATEWAY_ADMIN scope.
    """
    import logging as _lg

    from quart import jsonify

    from core.gateway.auth import extract_bearer, get_auth
    from core.gateway.scopes import Scope

    _logger = _lg.getLogger("gateway.auth")
    auth_hdr = request.headers.get("Authorization")
    xapi_hdr = request.headers.get("X-Api-Key")
    bearer = extract_bearer(auth_hdr, xapi_hdr)
    auth = get_auth()
    result = auth.check_request(
        bearer,
        request.remote_addr or "",
        allow_loopback_bypass=False,
    )
    if result is None or not auth.has_scope(result, Scope.GATEWAY_ADMIN):
        # Diagnostic log: makes root-causing 401s tractable without
        # leaking the secret itself.
        _logger.warning(
            "[mutation_auth] 401 path=%s auth_hdr=%s xapi=%s bearer_len=%d known_key_ids=%s result=%s",
            getattr(request, "path", "?"),
            "set" if auth_hdr else "absent",
            "set" if xapi_hdr else "absent",
            len(bearer) if bearer else 0,
            [k for k, *_ in auth._keys],
            None if result is None else {"key_id": result.key_id, "scopes": list(result.scopes)},
        )
        return jsonify({"error": "Unauthorized"}), 401
    return None


def require_admin_scope():
    """Reject requests whose API-key info lacks the ``admin`` scope.

    Routes called without an API key (e.g. PIN-authenticated browser session)
    have no ``api_key_info`` attribute on the request and are passed through.
    """
    key_info = getattr(request, "api_key_info", None)
    if key_info and not key_has_scope(key_info, "admin"):
        return api_error("Insufficient scope: requires 'admin'", 403)
    return None


def require_local(label: str):
    """Reject non-localhost callers for sensitive admin operations.

    ``label`` is used to build a user-readable error message, e.g.
    ``require_local("Extension install")`` → "Extension install is only
    available from localhost".

    Use for operations that should never be exposed beyond the local box
    even with valid credentials (install, uninstall, log download, etc.).
    """
    from core.web.auth_core import is_local_request

    if not is_local_request():
        return api_error(f"{label} is only available from localhost", 403)
    return None


def require_pin():
    """Reject requests when PIN is configured but the session is not authed.

    PIN-only gating: when ``PIN_AUTH`` is unset, profiles/settings are open
    (single-user case). When PIN is set, the user must have completed the
    PIN check flow earlier in the session.
    """
    if not current_app.config.get("PIN_AUTH"):
        return None
    if not session.get("pin_ok"):
        return api_error("認証が必要です", 401, code="pin_auth_required")
    return None
