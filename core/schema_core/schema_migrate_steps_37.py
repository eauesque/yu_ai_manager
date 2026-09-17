"""Schema migration 37: trophies table (trophy system DB persistence)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_37(con: sqlite3.Connection) -> None:
    """Create the trophies table."""
    logger.info("  -> Migration 37: trophies table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS trophies (
            id            INTEGER PRIMARY KEY,
            trophy_type   TEXT NOT NULL UNIQUE,
            title         TEXT NOT NULL,
            tier          TEXT NOT NULL DEFAULT 'gold',
            category      TEXT NOT NULL DEFAULT 'milestone',
            achieved_month TEXT,
            achieved_at   INTEGER NOT NULL,
            metadata      TEXT DEFAULT '{}'
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_trophies_category "
        "ON trophies(category)"
    )

    set_schema_version(con, 37, "trophies table for achievement system")
