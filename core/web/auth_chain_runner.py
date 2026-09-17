"""Execution order for the authentication chain."""


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

_STATIC_CHECKS = [check_static_bypass, check_share_bypass, check_pin_bypass]


def run_chain(
    path: str,
    method: str,
    auth_header: str,
    is_locked: bool,
    trusted_proxy_enabled: bool,
    remote_addr: str,
    trusted_ips: set,
    remote_user_header: str,
    session_pin_ok: bool,
    cookie_token: str,
    valid_token: str,
) -> AuthResult | None:
    for check_fn in _STATIC_CHECKS:
        result = check_fn(path)
        if result is not None:
            return result

    result = check_loopback_status_bypass(path, method, remote_addr)
    if result is not None:
        return result

    result = check_trusted_peer(path, remote_addr, is_locked)
    if result is not None:
        return result

    result = check_api_key(path, method, auth_header)
    if result is not None:
        return result

    result = check_quick_lock(is_locked, path)
    if result is not None:
        return result

    result = check_trusted_proxy(trusted_proxy_enabled, remote_addr, trusted_ips, remote_user_header)
    if result is not None:
        return result

    result = check_session(session_pin_ok)
    if result is not None:
        return result

    result = check_cookie(cookie_token, valid_token)
    if result is not None:
        return result

    return None
