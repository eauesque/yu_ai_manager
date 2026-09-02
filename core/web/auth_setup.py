"""Server auth setup API."""

import logging
import os
from datetime import timedelta

from quart import Quart

from core.web.auth_core import is_truthy_env
from core.web.auth_routes import register_pin_auth_routes, register_quick_lock_routes
from core.web.restart_routes import register_restart_route

logger = logging.getLogger(__name__)


def _coerce_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"1", "true", "yes", "on", "enabled"}:
            return True
        if s in {"0", "false", "no", "off", "disabled"}:
            return False
        return default
    return bool(value)


def setup_auth(app: Quart, pin: str | None = None, server_cfg: dict | None = None):
    """Configure PIN authentication and QuickLock on the Quart app."""
    cfg = server_cfg or {}
    app.config["PIN_AUTH"] = bool(pin)
    app.config["QUICK_LOCK_ENABLED"] = _coerce_bool(
        cfg.get("quick_lock_enabled"), True
    )
    app.config["PIN_BOSS_LOGIN_UI"] = _coerce_bool(cfg.get("pin_boss_login_ui"), True)
    app.config["TRUSTED_PROXY_AUTH"] = _coerce_bool(cfg.get("trusted_proxy_auth"), False)
    # Default to empty set — trusted_proxy_ips must be explicitly configured.
    # Including 127.0.0.1 by default is unsafe when binding to 0.0.0.0
    # because local services could spoof the X-Remote-User header.
    app.config["TRUSTED_PROXY_IPS"] = set(cfg.get("trusted_proxy_ips", []))
    app.config["TRUSTED_PROXY_HEADER"] = cfg.get("trusted_proxy_header", "X-Remote-User")
    if "RESTART_ENV_ENABLED" not in app.config:
        app.config["RESTART_ENV_ENABLED"] = is_truthy_env(os.environ.get("TAGDB_ALLOW_RESTART"))
    if "RESTART_ENABLE_SOURCE" not in app.config:
        app.config["RESTART_ENABLE_SOURCE"] = "env" if app.config.get("RESTART_ENV_ENABLED") else "none"

    if not app.secret_key:
        app.secret_key = os.urandom(24)

    # Harden session cookie security
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    # Session expiration (default 24 hours)
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=24))
    # Force HTTPS cookies when exposed on LAN or bound externally
    _host = cfg.get("host", "127.0.0.1")
    if cfg.get("lan") or _host in ("0.0.0.0", "::"):
        app.config.setdefault("SESSION_COOKIE_SECURE", True)

    secret = app.secret_key if isinstance(app.secret_key, str) else app.secret_key.hex()

    try:
        from core.sse.auth import configure_sse_auth

        configure_sse_auth(secret, int(cfg.get("port", 5000)))
    except Exception:
        logger.warning("web startup step failed", exc_info=True)

    register_pin_auth_routes(app, pin, secret)
    register_quick_lock_routes(app, pin, secret)
    register_restart_route(app)
