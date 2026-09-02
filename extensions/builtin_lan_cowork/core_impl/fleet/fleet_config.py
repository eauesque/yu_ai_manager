"""Fleet config helpers — allowlist union-type parser, timings."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TIMING_DEFAULTS = {
    # chief_observation_sec: HEARTBEAT_INTERVAL(10) * 2 + 5 jitter = 25
    "chief_observation_sec": 25,
    "peers_poll_interval_sec": 30,
    "heartbeat_timeout_sec": 60,
    "update_job_timeout_sec": 600,
    "postcheck_timeout_sec": 180,
    # consent_timeout_sec: seconds a peer consent token remains valid
    "consent_timeout_sec": 300,
    # soft_prune_sec: peers not reached within this window are skipped during
    # polling (still kept in DB; will recover on heartbeat / manual refresh).
    "soft_prune_sec": 3600,        # 1 hour
    # hard_prune_sec: peers not reached within this window are deleted from
    # the peers table on next startup. Tracks DHCP rotation churn.
    "hard_prune_sec": 7 * 86400,   # 7 days
}

# Module-level defaults used by registry._load_all (which runs before any
# manager-bound fleet_cfg exists). Keep in sync with _TIMING_DEFAULTS.
DEFAULT_SOFT_PRUNE_SEC = 3600
DEFAULT_HARD_PRUNE_SEC = 7 * 86400


def parse_allowlist(entries: list) -> list[dict]:
    """Normalize allowlist entries to [{peer_id: ...}] form.

    Strings are treated as peer_id shorthand.
    {role: ...} entries are logged as invalid and dropped (Phase 2 feature).
    Unknown dict shapes are also dropped.
    """
    result = []
    for entry in entries:
        if isinstance(entry, str):
            result.append({"peer_id": entry})
        elif isinstance(entry, dict):
            if "peer_id" in entry:
                result.append({"peer_id": entry["peer_id"]})
            elif "role" in entry:
                logger.warning(
                    "invalid_allowlist_entry: {role: ...} is a Phase 2 feature, ignoring: %s", entry
                )
            else:
                logger.warning(
                    "invalid_allowlist_entry: unknown allowlist entry shape, ignoring: %s", entry
                )
        else:
            logger.warning("invalid_allowlist_entry: unexpected type %s, ignoring", type(entry))
    return result


def peer_id_in_allowlist(peer_id: str, parsed: list[dict]) -> bool:
    """Return True if peer_id matches any entry in a parsed allowlist."""
    return any(e.get("peer_id") == peer_id for e in parsed)


def get_fleet_timings(fleet_cfg: dict) -> dict:
    """Return timings dict with defaults applied."""
    overrides = fleet_cfg.get("timings", {}) or {}
    return {k: overrides.get(k, v) for k, v in _TIMING_DEFAULTS.items()}


def get_fleet_cfg(mgr) -> dict:
    """Extract fleet config dict from manager.

    mgr.config is already the builtin-lan-cowork extension config;
    fleet settings live at mgr.config["fleet"].
    """
    cfg = getattr(mgr, "config", {}) or {}
    return cfg.get("fleet", {}) or {}
