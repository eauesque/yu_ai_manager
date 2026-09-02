"""Request hook registration for the Quart app factory."""

from __future__ import annotations

import hashlib
import re
import secrets
import time
import uuid

from quart import Quart, g, make_response, request

from core.infra_core.api_errors import api_error
from core.infra_core.debug_log import dlog, is_debug_enabled
from core.web.api_rate_limit import classify as classify_rate_limit
from core.web.api_rate_limit import get_client_ip
from core.web.proxy_prefixes import is_proxy_path
from core.web.security_headers import apply_security_headers

_CSRF_SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))
_CSRF_EXEMPT_PATHS_EXACT = ("/_pin_check",)
# /v1/* is the LLM router — it has its own auth, skip yu_ai_manager CSRF/rate-limit
_CSRF_EXEMPT_PATHS_PREFIX = ("/api/webhooks/receive/", "/v1/")
# OpenAI-compatible extension endpoints (/ext/<name>/v1/*) skip CSRF;
# they rely on trusted_peer / API-key auth (auth_chain.check_trusted_peer).
_CSRF_EXEMPT_EXT_V1_RE = re.compile(r"^/ext/[A-Za-z0-9][\w\-]*/v1/")


def get_csrf_description() -> str:
    """Return a human-readable CSRF summary derived from implementation constants.

    Generated from _CSRF_SAFE_METHODS, _CSRF_EXEMPT_PATHS_PREFIX, and
    _CSRF_EXEMPT_EXT_V1_RE — the single source of truth in this module.
    Used by routes/ai_context.py to populate csrf_note without coupling
    infra_core to web-layer imports.
    """
    safe = ", ".join(sorted(_CSRF_SAFE_METHODS))
    exempt_prefixes = ", ".join(_CSRF_EXEMPT_PATHS_PREFIX)
    return (
        f"POST/PUT/DELETE リクエストには X-Requested-With: XMLHttpRequest ヘッダが必要。"
        f"Bearer API Key 認証時は不要。"
        f"安全メソッド ({safe}) は CSRF チェック対象外。"
        f"除外パスプレフィックス: {exempt_prefixes}。"
        f"/ext/<name>/v1/* も除外（{_CSRF_EXEMPT_EXT_V1_RE.pattern}）。"
    )


def register_request_hooks(app: Quart) -> None:
    """Register CSRF, rate-limit, debug, CSP, and response hooks."""

    @app.before_request
    async def _ensure_request_id():
        if not getattr(g, "request_id", None):
            g.request_id = uuid.uuid4().hex[:8]
        if not getattr(g, "request_started_at", None):
            g.request_started_at = time.time()

    @app.before_request
    async def _check_csrf_header():
        if request.method in _CSRF_SAFE_METHODS:
            return
        if is_proxy_path(request.path):
            if (request.headers.get("Authorization", "").startswith("Bearer ")
                    or request.headers.get("Proxy-Authorization", "").startswith("Bearer ")):
                return
            return api_error(
                "CSRF header missing",
                status=403,
                code="csrf_header_missing",
            )
        if (not request.path.startswith("/api/")
                and not request.path.startswith("/ext/")
                and request.path not in _CSRF_EXEMPT_PATHS_EXACT):
            return
        if request.path in _CSRF_EXEMPT_PATHS_EXACT:
            return
        if any(request.path.startswith(p) for p in _CSRF_EXEMPT_PATHS_PREFIX):
            return
        if _CSRF_EXEMPT_EXT_V1_RE.match(request.path):
            return
        if request.headers.get("Authorization", "").startswith("Bearer "):
            return
        if request.path.startswith("/api/events/"):
            return
        if not request.headers.get("X-Requested-With"):
            return api_error(
                "CSRF header missing",
                status=403,
                code="csrf_header_missing",
            )

    @app.before_request
    async def _check_api_rate_limit():
        limiter = classify_rate_limit(request.method, request.path)
        if limiter is None:
            return
        ip = get_client_ip()
        allowed, _remaining = limiter.check(ip)
        if not allowed:
            body, status_code = api_error(
                "Rate limit exceeded",
                status=429,
                code="rate_limit_exceeded",
            )
            resp = await make_response(body, status_code)
            resp.headers["Retry-After"] = str(max(1, int(1.0 / limiter.rate)))
            return resp

    @app.before_request
    async def _debug_before_request():
        if not is_debug_enabled():
            return
        dlog(
            "web",
            "request.start",
            request_id=g.request_id,
            method=request.method,
            path=request.path,
            remote=request.remote_addr,
            query=request.query_string.decode("utf-8", errors="ignore"),
        )

    @app.before_request
    async def _generate_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    async def _inject_csp_nonce():
        return {
            "csp_nonce": getattr(g, "csp_nonce", ""),
            "pin_policy_warn": bool(app.config.get("PIN_POLICY_WARN")),
        }

    @app.after_request
    async def _set_security_headers(response):
        return apply_security_headers(app, response)

    @app.after_request
    async def _add_api_etag(response):
        if (
            request.method == "GET"
            and request.path.startswith("/api/")
            and response.status_code == 200
            and response.content_type
            and "json" in response.content_type
        ):
            data = await response.get_data()
            # ETag only, not crypto.
            etag = f'"{hashlib.md5(data, usedforsecurity=False).hexdigest()}"'  # nosemgrep: python.lang.security.insecure-hash-algorithms-md5
            response.headers["ETag"] = etag
            if request.headers.get("If-None-Match") == etag:
                response.status_code = 304
                response.set_data(b"")
        return response

    @app.after_request
    async def _debug_after_request(response):
        if not is_debug_enabled():
            return response
        rid = getattr(g, "request_id", "-")
        started = getattr(g, "request_started_at", None)
        elapsed_ms = int((time.time() - started) * 1000) if started else None
        dlog(
            "web",
            "request.end",
            request_id=rid,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        return response
