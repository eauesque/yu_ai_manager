"""Schema migration 42: Add OCR results table.

Add file_ocr_results table to store VLM OCR text extraction results.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_42(con: sqlite3.Connection) -> None:
    """Add OCR results table."""
    logger.info("  -> Migration 42: file_ocr_results table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS file_ocr_results (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            engine TEXT NOT NULL,
            task TEXT NOT NULL DEFAULT 'ocr',
            regions_json TEXT,
            full_text TEXT,
            structured_json TEXT,
            language TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(id),
            UNIQUE(file_id, engine, task)
        )
    """)

    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_ocr_file_id
        ON file_ocr_results(file_id)
    """)

    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_ocr_task
        ON file_ocr_results(task)
    """)

    # Speed up OCR full-text search with FTS5
    try:
        con.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts
            USING fts5(
                full_text,
                content='file_ocr_results',
                content_rowid='id',
                tokenize="unicode61"
            )
        """)
        con.execute("""
            CREATE TRIGGER IF NOT EXISTS ocr_fts_ai
            AFTER INSERT ON file_ocr_results BEGIN
                INSERT INTO ocr_text_fts(rowid, full_text)
                VALUES (new.id, new.full_text);
            END
        """)
        con.execute("""
            CREATE TRIGGER IF NOT EXISTS ocr_fts_ad
            AFTER DELETE ON file_ocr_results BEGIN
                INSERT INTO ocr_text_fts(ocr_text_fts, rowid, full_text)
                VALUES ('delete', old.id, old.full_text);
            END
        """)
        con.execute("""
            CREATE TRIGGER IF NOT EXISTS ocr_fts_au
            AFTER UPDATE OF full_text ON file_ocr_results BEGIN
                INSERT INTO ocr_text_fts(ocr_text_fts, rowid, full_text)
                VALUES ('delete', old.id, old.full_text);
                INSERT INTO ocr_text_fts(rowid, full_text)
                VALUES (new.id, new.full_text);
            END
        """)
    except Exception as exc:
        logger.warning("  -> ocr_text_fts creation skipped: %s", exc)

    set_schema_version(con, 42, "file_ocr_results table + FTS")


def _safe_index(con: sqlite3.Connection, sql: str) -> None:
    try:
        con.execute(sql)
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            logger.warning("  -> Index creation skipped: %s", exc)
