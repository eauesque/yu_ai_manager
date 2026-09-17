"""Asynchronous helpers for agent action journal writes."""

from __future__ import annotations

import json
import logging

from core.agent_safety.action_journal import record_action

_logger = logging.getLogger(__name__)


def log_peer_ip_migration(peer_id: str, old_ip: str, new_ip: str) -> None:
    """Record observed peer IP migration in agent_action_journal."""
    from core.services_core.db_write import submit_db_write_no_wait

    payload = json.dumps({"peer_id": peer_id, "old": old_ip, "new": new_ip})

    def _write() -> None:
        from core.services_core.db_state import get_db

        con = get_db()
        con.execute(
            """INSERT INTO agent_action_journal (action, details, created_at)
               VALUES ('peer_ip_migration_observed', ?, strftime('%s','now'))""",
            (payload,),
        )
        con.commit()

    submit_db_write_no_wait(_write)


def log_fleet_permission_change(
    changed_by_session: str,
    peer_id: str,
    before: dict,  # {"restart": bool, "update": bool, "log_stream": bool}
    after: dict,   # {"restart": bool, "update": bool, "log_stream": bool}
) -> None:
    """Record a per-peer fleet permission change in the action journal."""
    try:
        record_action(
            session_id=changed_by_session,
            tool_name="fleet.permissions.update",
            params={"peer_id": peer_id, "before": before, "after": after},
            result_summary=f"fleet permissions updated for {peer_id}",
            status="success",
            reversible=True,
            undo_params={"peer_id": peer_id, "restore": before},
        )
    except Exception as exc:
        _logger.debug("log_fleet_permission_change failed: %s", exc)


def log_fleet_master_switch(
    changed_by_session: str,
    before: bool,
    after: bool,
) -> None:
    """Record a fleet master switch (allow_remote_update) change.
    Only call when value actually changes (before != after).
    """
    try:
        record_action(
            session_id=changed_by_session,
            tool_name="fleet.permissions.master_switch",
            params={"before": before, "after": after},
            result_summary=f"fleet master switch set to {after}",
            status="success",
            reversible=True,
            undo_params={"restore": before},
        )
    except Exception as exc:
        _logger.debug("log_fleet_master_switch failed: %s", exc)
