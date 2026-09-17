"""Individual authentication checks used by auth_chain."""

import ipaddress
import logging
import re
from dataclasses import dataclass
from typing import Any

from core.web.auth_route_policy import match_declared_bypass
from core.web.proxy_prefixes import is_proxy_path


@dataclass
class AuthResult:
    passed: bool = False
    response: Any = None
    reason: str = ""


logger = logging.getLogger("core.web.auth_chain")
_EXT_NAME_RE = re.compile(r"^[A-Za-z0-9][\w\-]*$")


def _is_gateway_bypass(path: str) -> bool:
    if is_proxy_path(path):
        return True
    if path == "/api/gateway/keys" or path.startswith("/api/gateway/keys/"):
        return True
    if path == "/api/gateway/auth/reload":
        return True
    return path.startswith("/agentmemory/")


def check_static_bypass(path: str) -> AuthResult | None:
    if path.startswith("/static/") or path == "/favicon.ico":
        return AuthResult(passed=True, reason="static")
    if path.startswith("/help") or path.startswith("/api/help/"):
        return AuthResult(passed=True, reason="help")
    if path.startswith("/mcp"):
        return AuthResult(passed=True, reason="mcp")
    if path.startswith("/v1/"):
        return AuthResult(passed=True, reason="llm_router")
    if _is_gateway_bypass(path):
        return AuthResult(passed=True, reason="gateway")
    declared = match_declared_bypass(path)
    if declared is not None:
        return AuthResult(passed=True, reason=declared.require)
    if path in ("/api/mdns/identity", "/api/mdns/peers"):
        return AuthResult(passed=True, reason="mdns_identity")
    if path.startswith("/api/webhooks/receive/"):
        return AuthResult(passed=True, reason="webhook_inbound")
    return None


def check_trusted_peer(path: str, remote_addr: str, is_locked: bool) -> AuthResult | None:
    parts = path.split("/", 4)
    if len(parts) < 5 or parts[1] != "ext" or parts[3] != "v1":
        return None
    if not _EXT_NAME_RE.match(parts[2]):
        return None
    try:
        from core.web.trusted_peer_registry import get_registry

        registry = get_registry()
        if not registry.contains(remote_addr):
            return None
        if registry.is_loopback(remote_addr):
            return AuthResult(passed=True, reason="trusted_peer_loopback")
        if is_locked:
            return None
        return AuthResult(passed=True, reason="trusted_peer")
    except Exception as exc:  # pragma: no cover
        logger.warning("[auth] trusted_peer check failed: %s", exc)
    return None


def check_share_bypass(path: str) -> AuthResult | None:
    if path.startswith("/s/"):
        return AuthResult(passed=True, reason="share")
    return None


def check_pin_bypass(path: str) -> AuthResult | None:
    if path in ("/_pin", "/api/lock/status"):
        return AuthResult(passed=True, reason="pin_endpoint")
    return None


def check_loopback_status_bypass(path: str, method: str, remote_addr: str) -> AuthResult | None:
    if path != "/api/llm_router/status" or method != "GET":
        return None
    if (remote_addr or "").strip().lower() not in {"127.0.0.1", "::1", "localhost"}:
        return None
    return AuthResult(passed=True, reason="llm_router_status_loopback")


def check_api_key(path: str, method: str, auth_header: str) -> AuthResult | None:
    is_api = path.startswith("/api/") or ("/api/" in path and path.startswith("/ext/"))
    if is_api and auth_header.startswith("Bearer "):
        return AuthResult(passed=True, reason="api_key_candidate")
    return None


def check_quick_lock(is_locked: bool, path: str) -> AuthResult | None:
    if not is_locked:
        return None
    if path == "/api/lock/unlock":
        return AuthResult(passed=True, reason="lock_unlock")
    return AuthResult(passed=False, reason="locked")


def _ip_in_trusted(addr: str, trusted: set) -> bool:
    if addr in trusted:
        return True
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    for entry in trusted:
        if "/" in entry:
            try:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
    return False


def check_trusted_proxy(enabled: bool, remote_addr: str, trusted_ips: set, remote_user_header: str) -> AuthResult | None:
    if not enabled:
        return None
    if not _ip_in_trusted(remote_addr, trusted_ips):
        return None
    user = remote_user_header.strip()
    if not user:
        return None
    if any(c < " " or c == "\x7f" for c in user):
        return None
    return AuthResult(passed=True, reason="trusted_proxy")


def check_session(pin_ok: bool) -> AuthResult | None:
    if pin_ok:
        return AuthResult(passed=True, reason="session")
    return None


def check_cookie(cookie_token: str, valid_token: str) -> AuthResult | None:
    import hmac

    if cookie_token and valid_token and hmac.compare_digest(cookie_token, valid_token):
        return AuthResult(passed=True, reason="cookie")
    return None
