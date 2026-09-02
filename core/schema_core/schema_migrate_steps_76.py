"""Migration 76: add agent_circuit_breaker_state and agent_budget_usage tables.

These tables enable cross-process state visibility for Agent Safety components.
Each process (web / mcp) writes its own row directly; the other side reads
read-only.  No inter-process calls — COVENANT-compliant.
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_76(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 76: add agent_circuit_breaker_state and agent_budget_usage")

    con.execute("""
        CREATE TABLE IF NOT EXISTS agent_circuit_breaker_state (
            process_id    TEXT PRIMARY KEY,
            state         TEXT NOT NULL DEFAULT 'CLOSED',
            open_reason   TEXT NOT NULL DEFAULT '',
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_updated  TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS agent_budget_usage (
            session_id       TEXT NOT NULL,
            process_id       TEXT NOT NULL,
            used_total       INTEGER NOT NULL DEFAULT 0,
            used_write       INTEGER NOT NULL DEFAULT 0,
            used_destructive INTEGER NOT NULL DEFAULT 0,
            last_updated     TEXT NOT NULL,
            PRIMARY KEY (session_id, process_id)
        )
    """)

    # Do NOT call con.commit() here — schema_migrate_registry manages transactions.
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (76,)
    ).fetchone()
    if row is None:
        set_schema_version(
            con, 76,
            "add agent_circuit_breaker_state and agent_budget_usage tables",
        )
