"""Schema migration 35: Tag dictionary table (for Danbooru tag completion)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_35(con: sqlite3.Connection) -> None:
    """Create the tag dictionary table."""
    logger.info("  -> Migration 35: Tag dictionary table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS tag_dictionary (
            id         INTEGER PRIMARY KEY,
            tag_name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
            category   INTEGER NOT NULL DEFAULT 0,
            post_count INTEGER NOT NULL DEFAULT 0,
            aliases    TEXT DEFAULT ''
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_tagdict_post_count "
        "ON tag_dictionary(post_count DESC)"
    )

    set_schema_version(con, 35, "Tag dictionary table")
