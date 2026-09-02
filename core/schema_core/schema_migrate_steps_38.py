"""Schema migration 38: extension_schema_versions table (extension DB migration management)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_38(con: sqlite3.Connection) -> None:
    """Create version management table for extension-specific tables."""
    logger.info("  -> Migration 38: extension_schema_versions table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS extension_schema_versions (
            extension_name  TEXT NOT NULL,
            version         INTEGER NOT NULL,
            applied_at      INTEGER NOT NULL,
            description     TEXT DEFAULT '',
            PRIMARY KEY (extension_name, version)
        )
    """)

    set_schema_version(con, 38, "extension_schema_versions table for extension DB migrations")
