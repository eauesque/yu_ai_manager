"""Schema migration 24: Add scan_errors table for encoding/timeout error tracking."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_24(con: sqlite3.Connection) -> None:
    """Create scan_errors table for persistent scan error tracking."""
    logger.info("  -> Migration 24: Adding scan_errors table")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS scan_errors (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            path         TEXT NOT NULL,
            error_type   TEXT NOT NULL,
            error_detail TEXT,
            encodings_tried TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            resolved     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_scan_errors_type
            ON scan_errors(error_type);
        CREATE INDEX IF NOT EXISTS idx_scan_errors_resolved
            ON scan_errors(resolved);
        CREATE INDEX IF NOT EXISTS idx_scan_errors_path
            ON scan_errors(path);
    """)
    set_schema_version(con, 24, "Add scan_errors table for encoding/timeout error tracking")
