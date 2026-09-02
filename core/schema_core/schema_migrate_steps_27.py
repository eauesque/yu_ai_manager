"""Schema migration 27: Add description column to analysis table."""

import contextlib
import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_27(con: sqlite3.Connection) -> None:
    """Add description column to analysis table for image content description."""
    logger.info("  -> Migration 27: Adding description column to analysis table")
    with contextlib.suppress(Exception):  # column may already exist
        con.execute("ALTER TABLE analysis ADD COLUMN description TEXT")
    set_schema_version(con, 27, "Add description column to analysis")
