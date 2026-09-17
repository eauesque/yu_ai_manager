"""Schema migration 43: Add translation results table.

Add file_translations table to store translations of OCR results.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_43(con: sqlite3.Connection) -> None:
    """Add translation results table."""
    logger.info("  -> Migration 43: file_translations table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS file_translations (
            id INTEGER PRIMARY KEY,
            ocr_result_id INTEGER NOT NULL,
            target_lang TEXT NOT NULL,
            translated_text TEXT,
            region_translations_json TEXT,
            engine TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (ocr_result_id) REFERENCES file_ocr_results(id),
            UNIQUE(ocr_result_id, target_lang)
        )
    """)

    try:
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_translations_ocr_result
            ON file_translations(ocr_result_id)
        """)
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            logger.warning("  -> Index creation skipped: %s", exc)

    set_schema_version(con, 43, "file_translations table")
