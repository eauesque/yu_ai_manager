"""Migration 74: gateway_status_transitions table."""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_74(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 74: gateway_status_transitions")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS gateway_status_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backend_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            from_state TEXT NOT NULL
                CHECK (from_state IN ('running','stopped','unknown')),
            to_state TEXT NOT NULL
                CHECK (to_state IN ('running','stopped')),
            last_request_id TEXT,
            metadata TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_status_backend_time
            ON gateway_status_transitions(backend_id, timestamp DESC);
    """)
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (74,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 74, "gateway_status_transitions table")
