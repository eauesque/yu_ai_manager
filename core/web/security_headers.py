"""Security response headers (CSP, HSTS, cache policy) for the web app.

Split out of ``core/web/request_hooks.py`` to keep that file inside its size
budget (tests/basic/test_python_structure_guards). The hook registration still
lives there; only the header-building body moved, unchanged in behaviour.
"""

from __future__ import annotations

import logging

from quart import g, request

from core.web.api_rate_limit import get_client_ip
from core.web.public_host import resolve_public_host

logger = logging.getLogger(__name__)


def _build_connect_src() -> str:
    """connect-src for the CSP, widened to reach the SSE server's own port.

    The SSE server listens on a different port, so 'self' alone would block it.
    Any failure here falls back to 'self': a missing SSE origin degrades the
    live-update channel, while a raised exception would drop every header.
    """
    connect_src = "'self'"
    try:
        from core.sse.sse_server import get_sse_port

        sse_port = get_sse_port()
        if sse_port is None:
            return connect_src

        host = resolve_public_host(get_client_ip())
        sse_hosts = {host}
        # Loopback access can arrive via either 127.0.0.1 or localhost; the SSE
        # client mirrors window.location.hostname, so allow both. CSP source
        # lists do not accept bracketed IPv6 literals, so only the textual
        # loopback hosts are registered here.
        if host in {"127.0.0.1", "::1", "localhost"}:
            sse_hosts.update({"127.0.0.1", "localhost"})
        # Also allow the hostname the browser actually used (e.g. pi2.local via
        # mDNS) so SSE connects via that same hostname aren't blocked.
        req_host = (request.host or "").split(":")[0].strip().lower()
        if req_host and req_host not in {"0.0.0.0", "::"}:
            sse_hosts.add(req_host)
        for sse_host in sse_hosts:
            connect_src += f" http://{sse_host}:{sse_port}"
    except Exception:
        logger.warning("web startup step failed", exc_info=True)
    return connect_src


def _hsts_value(app) -> str | None:
    """Strict-Transport-Security value, or None when it must not be sent."""
    if not (app.config.get("HSTS_ENABLED") and request.scheme == "https"):
        return None
    max_age = max(0, int(app.config.get("HSTS_MAX_AGE", 31536000)))
    hsts = f"max-age={max_age}"
    if app.config.get("HSTS_INCLUDE_SUBDOMAINS", True):
        hsts += "; includeSubDomains"
    if app.config.get("HSTS_PRELOAD", False):
        hsts += "; preload"
    return hsts


def apply_security_headers(app, response):
    """Set the security/cache headers on an outgoing response."""
    response.headers.setdefault("X-Request-Id", getattr(g, "request_id", ""))
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")

    hsts = _hsts_value(app)
    if hsts is not None:
        response.headers.setdefault("Strict-Transport-Security", hsts)

    nonce = getattr(g, "csp_nonce", "")
    csp = (
        "default-src 'self'; "
        f"script-src 'strict-dynamic' 'nonce-{nonce}' 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        f"connect-src {_build_connect_src()}; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "trusted-types dompurify default"
    )
    response.headers.setdefault("Content-Security-Policy", csp)

    if request.path.endswith("/sw.js"):
        response.headers["Service-Worker-Allowed"] = "/"

    if request.path.startswith("/api/") and not request.path.startswith(
        ("/api/thumbnail/", "/api/file/", "/api/preview/", "/api/original/")
    ):
        if request.path.startswith("/api/search"):
            response.headers.setdefault("Cache-Control", "no-cache")
        else:
            response.headers.setdefault(
                "Cache-Control", "no-store, no-cache, must-revalidate"
            )
    return response
