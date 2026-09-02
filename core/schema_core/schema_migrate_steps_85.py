"""Migration 85: add agent_auto_approve_rules table.

Shared storage for Agent Safety auto-approve rules. The web process writes
(INSERT/DELETE); the MCP subprocess and the Rust server read read-only to
decide whether a tool call bypasses the HITL gate. Single-writer(web) /
multi-reader, no inter-process calls — COVENANT-compliant.

This replaces the prior config.json-backed in-memory list, where rules added at
runtime never reached the MCP subprocess (which loaded rules only at startup).
``conditions_json`` holds the rule's condition map; ordering is by ``id`` so the
index-based DELETE endpoint keeps working.
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_85(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 85: add agent_auto_approve_rules")

    con.execute("""
        CREATE TABLE IF NOT EXISTS agent_auto_approve_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tool            TEXT NOT NULL,
            conditions_json TEXT NOT NULL DEFAULT '{}',
            approved_at     TEXT NOT NULL,
            approved_by     TEXT NOT NULL DEFAULT 'user'
        )
    """)

    # Do NOT call con.commit() here — schema_migrate_registry manages transactions.
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (85,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 85, "add agent_auto_approve_rules table")
