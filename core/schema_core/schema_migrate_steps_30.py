"""Schema migration 30: Add source column to file_tags (meta/user tag separation)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version


def apply_migration_30(con: sqlite3.Connection) -> None:
    """Add source column to file_tags table to record tag origin."""
    logger.info("  -> Migration 30: Adding source column to file_tags")

    if not table_has_column(con, "file_tags", "source"):
        con.execute(
            "ALTER TABLE file_tags ADD COLUMN source TEXT NOT NULL DEFAULT 'meta'"
        )
    con.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_source ON file_tags(source)")

    set_schema_version(con, 30, "file_tags source column (meta/user tag layer)")
