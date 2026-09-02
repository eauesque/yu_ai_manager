"""Crypto Tools page route - browser-only encryption utility.

Backend serves the page only. All crypto happens client-side via Web Crypto API.
Spec: docs/superpowers/specs/2026-05-23-crypto-tools-design.md
"""

from __future__ import annotations

from quart import Blueprint, current_app, g, render_template, session

from core.infra_core.api_errors import api_error
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

bp = Blueprint("crypto_tools", __name__)


@bp.before_request
async def _auth():
    err = _require_admin_scope()
    if err:
        return err
    if current_app.config.get("PIN_AUTH") and not session.get("pin_ok"):
        return api_error("認証が必要です", 401, code="pin_auth_required")
    return None


@bp.after_request
async def _harden_csp(response):
    """Construct a stricter CSP for this page.

    Rationale: this page handles private keys client-side. An XSS would be
    catastrophic. We build the CSP from scratch (rather than mutating the
    global CSP set by core.web.request_hooks._set_security_headers) so the
    after_request ordering between blueprint and app does not affect us.

    Differences from the global CSP:
    - connect-src 'self' only (no cross-origin exfiltration; same-origin
      needed for nav.js API calls like /api/server-info and i18n JSON)
    - img-src strips blob: (we only need data: for canvas dataURLs)
    - frame-ancestors 'none' (no clickjacking)
    - script-src keeps nonce-{n} for nav inline scripts
    - style-src keeps 'unsafe-inline' (the nav uses inline styles)
    """
    nonce = getattr(g, "csp_nonce", "") or ""
    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "trusted-types dompurify default"
    )
    # Overwrite — do not setdefault — so we beat the global hook regardless
    # of after_request ordering.
    response.headers["Content-Security-Policy"] = csp
    return response


@bp.route("/crypto-tools")
async def crypto_tools_page():
    return await render_template("crypto_tools.html", active="crypto_tools")
