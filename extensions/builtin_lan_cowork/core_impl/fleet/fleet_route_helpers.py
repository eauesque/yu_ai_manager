"""Shared helpers used by fleet route registration."""
from __future__ import annotations


def get_fleet_cfg(mgr) -> dict:
    """Return the fleet config dict (empty dict if absent)."""
    from .fleet_config import get_fleet_cfg as _get_fleet_cfg

    return _get_fleet_cfg(mgr)


ALLOWLIST_CATEGORIES = {
    "log_stream": "allow_log_stream_from",
    "update": "allow_update_from",
}


def normalize_entries(entries) -> list[str]:
    """Return a list of peer_id strings from str or {peer_id: ...} entries."""
    out: list[str] = []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
        elif isinstance(entry, dict) and isinstance(entry.get("peer_id"), str) and entry["peer_id"].strip():
            out.append(entry["peer_id"].strip())
    seen: set[str] = set()
    result: list[str] = []
    for peer_id in out:
        if peer_id not in seen:
            seen.add(peer_id)
            result.append(peer_id)
    return result


def apply_allowlist_update(mgr, mutator) -> dict:
    """Load fleet config, run mutator(fleet_cfg), persist, and update live mgr.config."""
    from core.extensions_core.lifecycle.extensions_admin import (
        get_extension_config_value,
        save_extension_config_values,
    )

    ext_name = "builtin-lan-cowork"
    fleet_cfg = dict(get_extension_config_value(ext_name, "fleet", {}) or {})
    for key in ALLOWLIST_CATEGORIES.values():
        fleet_cfg[key] = normalize_entries(fleet_cfg.get(key, []))
    mutator(fleet_cfg)
    save_extension_config_values(ext_name, {"fleet": fleet_cfg})
    if mgr is not None and hasattr(mgr, "config") and isinstance(mgr.config, dict):
        live = mgr.config.setdefault("fleet", {})
        for key in ALLOWLIST_CATEGORIES.values():
            live[key] = list(fleet_cfg.get(key, []))
        if "allow_remote_update" in fleet_cfg:
            live["allow_remote_update"] = bool(fleet_cfg["allow_remote_update"])
    return fleet_cfg


def check_log_stream_allowed(
    requester_peer_id: str, fleet_cfg: dict
) -> tuple[bool, str]:
    """Return (allowed, reason) for streaming this node's logs to a peer.

    ``allow_remote_update`` is checked first. Its name is historical -- the UI
    calls it "リモートからのアップデートを有効にする（マスタースイッチ）" and
    check_update_allowed treats it as the master switch for all fleet
    operations -- but this function used to read only the allowlist. An
    operator who unchecked the master switch was told remote fleet access was
    off while log streaming, which ships this node's ring buffer to a remote
    peer, kept working.
    """
    from .fleet_config import parse_allowlist, peer_id_in_allowlist

    if not fleet_cfg.get("allow_remote_update", False):
        return False, "remote_update_disabled"
    raw = fleet_cfg.get("allow_log_stream_from", []) or []
    parsed = parse_allowlist(raw)
    if not peer_id_in_allowlist(requester_peer_id, parsed):
        return False, "not_in_allowlist"
    return True, ""


def build_peer_relay_url(peer, lines: int = 200, level: str | None = None) -> str:
    """Build the /fleet/logs/stream URL for a peer."""
    url = f"http://{peer.api_host}:{peer.api_port}/ext/lan_cowork/fleet/logs/stream?lines={lines}"
    if level:
        url += f"&level={level}"
    return url
