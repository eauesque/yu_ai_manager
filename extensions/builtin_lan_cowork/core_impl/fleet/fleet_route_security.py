"""Security and policy helpers shared by fleet route modules."""
from __future__ import annotations

from quart import current_app
from quart import session as quart_session


def make_session_checker(session_guard=None):
    def _session_ok() -> bool:
        if session_guard is not None:
            return session_guard()
        # Fallback: allow if no PIN auth configured
        try:
            if not current_app.config.get("PIN_AUTH"):
                return True
            return bool(quart_session.get("pin_ok"))
        except Exception:
            return False

    return _session_ok


async def check_update_allowed(
    mgr,
    requester_peer_id: str,
    *,
    fleet_cfg_getter,
    consume_consent_token,
    allow_consent: bool = True,
    include_restart_allowlist: bool = False,
    # NOTE: allow_remote_update is historically named for "update" but acts as
    # the master switch for ALL fleet operations (restart, update, log stream).
) -> tuple[bool, str]:
    from quart import request

    from .fleet_config import parse_allowlist, peer_id_in_allowlist

    fleet_cfg = fleet_cfg_getter(mgr)
    if not fleet_cfg.get("allow_remote_update", False):
        if allow_consent:
            consent_token = request.headers.get("X-Consent-Token", "").strip()
            if consent_token:
                if await consume_consent_token(consent_token, requester_peer_id):
                    return True, ""
                return False, "consent_token_invalid"
        return False, "remote_update_disabled"

    raw = fleet_cfg.get("allow_update_from", []) or []
    parsed = parse_allowlist(raw)
    local_id = mgr.local_peer.peer_id
    if requester_peer_id == local_id:
        return True, ""
    if peer_id_in_allowlist(requester_peer_id, parsed):
        return True, ""
    if include_restart_allowlist:
        restart_raw = fleet_cfg.get("allow_restart_from", []) or []
        restart_parsed = parse_allowlist(restart_raw)
        if peer_id_in_allowlist(requester_peer_id, restart_parsed):
            return True, ""
    return False, "not_in_allowlist"
