"""Schema migration 33: Add performance indexes (tuning for 1.5M files)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_33(con: sqlite3.Connection) -> None:
    """Batch-create performance indexes for large DB."""
    logger.info("  -> Migration 33: Adding performance indexes for 1.5M files")

    indexes = [
        ("CREATE INDEX IF NOT EXISTS idx_templates_file_id ON templates(file_id)",),
        ("CREATE INDEX IF NOT EXISTS idx_file_tags_tag_file ON file_tags(tag_id, file_id)",),
        ("CREATE INDEX IF NOT EXISTS idx_analysis_style ON analysis(style) WHERE style IS NOT NULL AND style != ''",),
        ("CREATE INDEX IF NOT EXISTS idx_files_size ON files(size) WHERE is_deleted=0 AND size > 1024",),
        ("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)",),
        ("CREATE INDEX IF NOT EXISTS idx_file_ratings_rating_file ON file_ratings(rating, file_id)",),
    ]
    for (sql,) in indexes:
        try:
            con.execute(sql)
        except Exception as e:
            logger.debug("Migration 33: skipped index (%s): %s", sql[:60], e)

    set_schema_version(con, 33, "Performance indexes for large DB")
