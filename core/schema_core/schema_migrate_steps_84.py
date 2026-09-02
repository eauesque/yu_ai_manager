"""Migration 84: add agent_session_scopes table.

Shared scope storage for cross-process Agent Safety enforcement. The web
process writes (UPSERT) session scopes; the MCP subprocess and the Rust server
read them read-only to enforce. Single-writer (web) / multi-reader, no
inter-process calls — COVENANT-compliant.

Unlike migration 76 (per-process-own-row keyed by process_id), this table is
keyed by session_id: a shared session->scope map. This fixes the enforcement
gap where a scope set via the web API never reached the MCP subprocess's
in-memory ScopeFence (which fell back to the default preset, fail-open).

denied_json stores the FULLY EXPANDED fnmatch deny patterns (preset deny list
plus any custom patterns), so readers (MCP, Rust) never need to interpret
preset names — they read the expanded list directly (parity-safe).
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_84(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 84: add agent_session_scopes")

    con.execute("""
        CREATE TABLE IF NOT EXISTS agent_session_scopes (
            session_id  TEXT PRIMARY KEY,
            preset      TEXT NOT NULL DEFAULT 'organizer',
            name        TEXT NOT NULL DEFAULT '',
            denied_json TEXT NOT NULL DEFAULT '[]',
            created_at  TEXT NOT NULL,
            expires_at  TEXT
        )
    """)

    # Do NOT call con.commit() here — schema_migrate_registry manages transactions.
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (84,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 84, "add agent_session_scopes table")
