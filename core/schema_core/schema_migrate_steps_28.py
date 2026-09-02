"""Schema migration 28: Create prompt_trend_history table."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_28(con: sqlite3.Connection) -> None:
    """Create prompt_trend_history table for storing trend analysis results."""
    logger.info("  -> Migration 28: Creating prompt_trend_history table")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_trend_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            engine       TEXT NOT NULL,
            analyzed_at  INTEGER NOT NULL,
            prompt_count INTEGER NOT NULL DEFAULT 0,
            result_json  TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pth_analyzed_at
            ON prompt_trend_history(analyzed_at DESC)
        """
    )
    set_schema_version(con, 28, "Create prompt_trend_history table")
