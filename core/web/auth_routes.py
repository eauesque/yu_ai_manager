import hmac as _hmac
import re

from quart import Quart, make_response, redirect, request, session

from core.infra_core.api_errors import api_error, api_result, api_success
from core.infra_core.api_request import require_json_dict
from core.web.auth_core import hash_pin, make_token, quick_lock, rate_limiter
from core.web.pages import render_lock_page, render_pin_page

# Minimum PIN length enforcement
_MIN_PIN_LENGTH = 4

# Open redirect: only allow safe relative paths
_SAFE_REDIRECT_RE = re.compile(r"^/[^/\\]")


def register_pin_auth_routes(app: Quart, pin: str | None, secret: str):
    if not pin:
        return

    pin_hash = hash_pin(pin, secret)
    valid_token = make_token(pin, secret)

    def _use_boss_login_ui() -> bool:
        return bool(app.config.get("PIN_BOSS_LOGIN_UI", True))

    async def _render_pin(error: str = "", next_url: str = ""):
        boss = _use_boss_login_ui()
        try:
            return await render_pin_page(error=error, boss_mode=boss, next_url=next_url)
        except TypeError:
            # Backward-compat: older render_pin_page(error) signature.
            return await render_pin_page(error=error)

    async def _render_lock():
        boss = _use_boss_login_ui()
        try:
            return await render_lock_page(boss_mode=boss)
        except TypeError:
            # Backward-compat: older render_lock_page() signature.
            return await render_lock_page()

    @app.before_request
    async def check_auth():
        from core.web.auth_chain import run_chain

        result = run_chain(
            path=request.path,
            method=request.method,
            auth_header=request.headers.get("Authorization", ""),
            is_locked=quick_lock.is_locked,
            trusted_proxy_enabled=bool(app.config.get("TRUSTED_PROXY_AUTH")),
            remote_addr=request.remote_addr,
            trusted_ips=app.config.get("TRUSTED_PROXY_IPS", set()),
            remote_user_header=request.headers.get(
                app.config.get("TRUSTED_PROXY_HEADER", "X-Remote-User"), ""
            ),
            session_pin_ok=bool(session.get("pin_ok")),
            cookie_token=request.cookies.get("pin_token", ""),
            valid_token=valid_token,
        )

        # run_chain returned None -- unauthenticated, show PIN page
        if result is None:
            if request.method == "POST" and request.path == "/_pin_check":
                return await _handle_pin_check(pin_hash, valid_token, secret)
            # Return JSON 401 for unauthenticated requests to API paths
            if request.path.startswith("/api/"):
                return api_error("認証が必要です", 401, code="pin_auth_required")
            next_url = request.path if request.method == "GET" and request.path != "/" else ""
            return await _render_pin(next_url=next_url)

        # Authentication OK
        if result.passed:
            # API Key -- additional auth, scope, and rate limit processing
            if result.reason == "api_key_candidate":
                # MCP internal token -- internal API calls from /mcp endpoint
                from core.web.apikey_auth.key_auth import extract_bearer_token
                _bearer = extract_bearer_token() or ""
                if _bearer.startswith("internal_"):
                    import hmac as _hmac_int

                    from routes.mcp_endpoint import get_internal_token
                    if _hmac_int.compare_digest(_bearer, f"internal_{get_internal_token()}"):
                        # Allow loopback addresses only.
                        from core.web.auth_restart import is_loopback_request
                        if not is_loopback_request():
                            return api_error("Internal token rejected: non-local", 403)
                        # Allow only MCP-related paths.
                        _path = request.path
                        if not (_path.startswith("/mcp") or _path.startswith("/api/mcp/")):
                            return api_error("Internal token scope limited", 403)
                        return  # Internal request: auth pass

                from core.web.apikey_auth.key_auth import authenticate_api_key, check_api_key_rate_limit
                from core.web.apikey_auth.key_scopes import get_required_scope, key_has_scope
                key_info = authenticate_api_key()
                if key_info:
                    allowed, remaining = check_api_key_rate_limit(key_info)
                    if not allowed:
                        return api_error("Rate limit exceeded", 429)
                    required_scope = get_required_scope(request.method, request.path)
                    if required_scope and not key_has_scope(key_info, required_scope):
                        return api_error(
                            f"Insufficient scope: requires '{required_scope}'", 403
                        )
                    request.api_key_info = key_info
                    return
                # Bearer header present but invalid for apikey_auth system.
                # Gateway routes (/api/gateway/*) use a separate auth system
                # (core.gateway.auth) — accept gateway admin tokens here so
                # the request reaches the gateway route handler, which
                # performs its own per-route scope check via
                # check_mutation_auth().
                if request.path.startswith("/api/gateway/"):
                    from core.gateway.auth import (
                        extract_bearer as _extract_bearer,
                    )
                    from core.gateway.auth import (
                        get_auth as _get_gw_auth,
                    )
                    from core.gateway.scopes import Scope as _GwScope
                    _gw_auth = _get_gw_auth()
                    _gw_bearer = _extract_bearer(
                        request.headers.get("Authorization"),
                        request.headers.get("X-Api-Key"),
                    )
                    _gw_result = _gw_auth.check_request(
                        _gw_bearer,
                        request.remote_addr or "",
                        allow_loopback_bypass=False,
                    )
                    if _gw_result is not None and _gw_auth.has_scope(_gw_result, _GwScope.GATEWAY_ADMIN):
                        return
                if request.path.startswith("/api/"):
                    return api_error("Invalid API key", 401)
                next_url = request.path if request.method == "GET" and request.path != "/" else ""
                return await _render_pin(next_url=next_url)

            # Trusted Proxy -- set session
            if result.reason == "trusted_proxy":
                session["pin_ok"] = True
                header = app.config.get("TRUSTED_PROXY_HEADER", "X-Remote-User")
                raw_user = request.headers.get(header, "").strip()
                # Sanitize: allow only alphanumeric, dash, underscore, dot, @
                session["remote_user"] = re.sub(r"[^\w.@-]", "", raw_user)[:128]

            # Cookie -- promote to session
            if result.reason == "cookie":
                session["pin_ok"] = True

            return  # Authentication passed

        # Authentication failed
        if result.reason == "locked":
            if request.path.startswith("/api/"):
                return api_error("locked", 423, extra={"message": "アプリはロック中です"})
            return await _render_lock()

    def _safe_redirect_target(url: str) -> str:
        """Validate redirect target to prevent open redirect."""
        if url and _SAFE_REDIRECT_RE.match(url):
            return url
        return "/"

    async def _handle_pin_check(pin_h: str, token: str, sec: str):
        from core.web.api_rate_limit import get_client_ip

        # Preserve next_url across error retries
        next_url = (await request.form).get('next', '')
        # Use get_client_ip() for proper proxy-aware rate limiting
        ip = get_client_ip()
        if not rate_limiter.check(ip):
            remaining = rate_limiter.remaining_seconds(ip)
            return await _render_pin(error=f"試行回数超過。{remaining}秒後にお試しください。", next_url=next_url)

        # CSRF token verification (compare without pop to avoid race condition)
        csrf_token = (await request.form).get('_csrf_token', '')
        expected = session.get('_csrf_token', '')
        if not expected or not _hmac.compare_digest(csrf_token, expected):
            return await _render_pin(error="セッションが無効です。再試行してください。", next_url=next_url)

        submitted = (await request.form).get('pin', '')
        # Enforce minimum PIN length
        if len(submitted) < _MIN_PIN_LENGTH:
            return await _render_pin(error=f"PINは{_MIN_PIN_LENGTH}文字以上必要です", next_url=next_url)
        from core.web.auth_lock_state import is_approval_pin_expired
        if is_approval_pin_expired():
            return await _render_pin(error="PIN の有効期限が切れています。管理者にお問い合わせください。", next_url=next_url)
        if _hmac.compare_digest(hash_pin(submitted, sec), pin_h):
            # Session fixation protection: regenerate session ID
            # Clear session data and generate new CSRF token to rotate session
            session.clear()
            session['pin_ok'] = True
            session.permanent = True
            # Force new session ID by setting a fresh nonce
            import os as _os
            session['_session_nonce'] = _os.urandom(16).hex()
            rate_limiter.clear(ip)
            quick_lock.unlock()
            # Redirect to the page the user originally requested
            redirect_to = _safe_redirect_target(next_url)
            resp = await make_response(redirect(redirect_to))
            resp.set_cookie('pin_token', token, max_age=86400, httponly=True,
                           samesite='Lax', secure=request.is_secure)
            return resp
        rate_limiter.record_failure(ip)
        attempts_left = rate_limiter.max_attempts - (rate_limiter._attempts.get(ip, (0,))[0])
        return await _render_pin(error=f"PINが違います（残り{max(0, attempts_left)}回）", next_url=next_url)

    @app.route('/_pin')
    async def pin_page():
        return await _render_pin()

    @app.route('/_pin_check', methods=['POST'])
    async def pin_check():
        if session.get('pin_ok'):
            next_url = (await request.form).get('next', '') or '/'
            next_url = _safe_redirect_target(next_url)
            return redirect(next_url)
        return await _handle_pin_check(pin_hash, valid_token, secret)


def register_quick_lock_routes(app: Quart, pin: str | None, secret: str):
    # Pre-compute PIN hash once (avoid re-hashing on every unlock attempt)
    _pin_hash = hash_pin(pin, secret) if pin else ""

    @app.route('/api/lock/activate', methods=['POST'])
    async def api_lock_activate():
        if not app.config.get('PIN_AUTH'):
            return api_error("PIN認証が設定されていません。ロックにはPINが必要です。", 400)
        if not app.config.get('QUICK_LOCK_ENABLED', True):
            return api_error("QuickLock は設定で無効化されています。", 400)
        quick_lock.lock()
        session.pop('pin_ok', None)
        return api_success({"success": True, "locked": True}, 200)

    @app.route('/api/lock/unlock', methods=['POST'])
    async def api_lock_unlock():
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        submitted_pin = data.get('pin', '')
        if not pin:
            return api_error("PIN not configured", 400)

        from core.web.api_rate_limit import get_client_ip
        ip = get_client_ip()
        if not rate_limiter.check(ip):
            remaining = rate_limiter.remaining_seconds(ip)
            return api_error(f"ロックアウト中（{remaining}秒）", 429)

        from core.web.auth_lock_state import is_approval_pin_expired
        if is_approval_pin_expired():
            return api_error("PIN の有効期限が切れています。管理者にお問い合わせください。", 403)
        if _hmac.compare_digest(hash_pin(submitted_pin, secret), _pin_hash):
            quick_lock.unlock()
            session['pin_ok'] = True
            rate_limiter.clear(ip)
            return api_success({"success": True, "locked": False}, 200)
        rate_limiter.record_failure(ip)
        return api_error("PINが違います", 401)

    @app.route('/api/lock/status')
    async def api_lock_status():
        """Return lock state. Whitelisted in before_request so it remains
        accessible while locked. Used for status polling from lock screen JS."""
        return api_result(quick_lock.info(), 200)

    @app.route('/api/auth/status')
    async def api_auth_status():
        """Return current authentication configuration."""
        return api_result({
            "pin_auth": bool(app.config.get("PIN_AUTH")),
            "quick_lock_enabled": bool(app.config.get("QUICK_LOCK_ENABLED", True)),
            "quick_lock_locked": quick_lock.is_locked,
            "trusted_proxy_auth": bool(app.config.get("TRUSTED_PROXY_AUTH")),
            "session_authenticated": bool(session.get("pin_ok")),
        }, 200)

    @app.route('/api/auth/logout', methods=['POST'])
    async def api_auth_logout():
        session.clear()
        success_resp, _ = api_success({"success": True}, 200)
        resp = await make_response(success_resp)
        resp.delete_cookie('pin_token')
        return resp
