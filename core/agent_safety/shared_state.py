"""Cross-process Agent Safety state persistence.

Each process (web / mcp) writes its own row directly to SQLite.
The other process reads as read-only.  No inter-process calls — COVENANT-compliant.

Tables (migration 76):
  agent_circuit_breaker_state  -- CB state per process_id
  agent_budget_usage           -- budget counters per (session_id, process_id)

Process identity is set via the YU_PROCESS_ID environment variable.
The MCP subprocess sets it to "mcp" in mcp_server/__main__.py.
The Web Server defaults to "web".
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Process identity — "mcp" when running as the MCP subprocess, "web" otherwise.
PROCESS_ID: str = os.environ.get("YU_PROCESS_ID", "web")


# ---------------------------------------------------------------------------
# Internal DB helper (mirrors action_journal._get_db pattern)
# ---------------------------------------------------------------------------

def _get_db():
    """Get DB connection via ServiceRegistry, with fallback for standalone MCP mode."""
    try:
        from core.extensions_core.service_registry import ServiceRegistry
        get_db_fn = ServiceRegistry.get("db")
        if callable(get_db_fn):
            return get_db_fn()
        if get_db_fn is not None:
            return get_db_fn  # type: ignore[return-value]
    except Exception as e:
        logger.debug("shared_state: ServiceRegistry.get('db') failed: %s", e)
    from core.services_core.db_state import get_db as _direct_get_db
    return _direct_get_db()


# ---------------------------------------------------------------------------
# Writers — called by CB / BudgetTracker when state changes.
# Fire-and-forget: any exception is swallowed so callers are never disrupted.
# ---------------------------------------------------------------------------

def write_cb_state(
    state: str,
    open_reason: str = "",
    failure_count: int = 0,
) -> None:
    """UPSERT this process's Circuit Breaker state row.

    Args:
        state:         "CLOSED" / "OPEN" / "HALF_OPEN"
        open_reason:   Human-readable trip reason (empty when CLOSED/HALF_OPEN).
        failure_count: Current consecutive error count.
    """
    try:
        db = _get_db()
        now = datetime.now(UTC).isoformat()
        db.execute(
            """INSERT INTO agent_circuit_breaker_state
               (process_id, state, open_reason, failure_count, last_updated)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(process_id) DO UPDATE SET
                 state         = excluded.state,
                 open_reason   = excluded.open_reason,
                 failure_count = excluded.failure_count,
                 last_updated  = excluded.last_updated""",
            (PROCESS_ID, state.upper(), open_reason, failure_count, now),
        )
        db.commit()
    except Exception as exc:
        logger.debug("shared_state.write_cb_state failed: %s", exc)


def write_budget_usage(
    session_id: str,
    used_total: int,
    used_write: int,
    used_destructive: int,
) -> None:
    """UPSERT this process's budget usage row for the given session."""
    try:
        db = _get_db()
        now = datetime.now(UTC).isoformat()
        db.execute(
            """INSERT INTO agent_budget_usage
               (session_id, process_id, used_total, used_write, used_destructive, last_updated)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, process_id) DO UPDATE SET
                 used_total       = excluded.used_total,
                 used_write       = excluded.used_write,
                 used_destructive = excluded.used_destructive,
                 last_updated     = excluded.last_updated""",
            (session_id, PROCESS_ID, used_total, used_write, used_destructive, now),
        )
        db.commit()
    except Exception as exc:
        logger.debug("shared_state.write_budget_usage failed: %s", exc)


# ---------------------------------------------------------------------------
# Readers — called by the Web Server's agent_status API.
# Return empty collections on any error so the API degrades gracefully.
# ---------------------------------------------------------------------------

def read_all_cb_states() -> list[dict[str, Any]]:
    """Return CB state rows for all known processes."""
    try:
        db = _get_db()
        rows = db.execute(
            """SELECT process_id, state, open_reason, failure_count, last_updated
               FROM agent_circuit_breaker_state
               ORDER BY process_id"""
        ).fetchall()
        return [
            {
                "process_id":    r[0],
                "state":         r[1],
                "open_reason":   r[2],
                "failure_count": r[3],
                "last_updated":  r[4],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("shared_state.read_all_cb_states failed: %s", exc)
        return []


def read_all_budget_usages(session_id: str) -> list[dict[str, Any]]:
    """Return budget usage rows for all processes for the given session."""
    try:
        db = _get_db()
        rows = db.execute(
            """SELECT process_id, used_total, used_write, used_destructive, last_updated
               FROM agent_budget_usage
               WHERE session_id = ?
               ORDER BY process_id""",
            (session_id,),
        ).fetchall()
        return [
            {
                "process_id":      r[0],
                "used_total":      r[1],
                "used_write":      r[2],
                "used_destructive": r[3],
                "last_updated":    r[4],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("shared_state.read_all_budget_usages failed: %s", exc)
        return []
