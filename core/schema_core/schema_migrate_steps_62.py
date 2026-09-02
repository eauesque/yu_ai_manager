"""Migration 62: Add clip_eligible_files helper table."""

import logging

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_62(con) -> None:
    """Create persistent helper table for CLIP-eligible file IDs."""
    logger.info("  -> Migration 62: create clip_eligible_files helper table")
    con.execute("""
        CREATE TABLE IF NOT EXISTS clip_eligible_files (
            file_id INTEGER PRIMARY KEY,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)
    set_schema_version(con, 62, "Add clip_eligible_files helper table")
