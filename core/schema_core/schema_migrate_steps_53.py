"""Migration 53: analysis / file_annotations large text columns converted to BLOB type.

To enable zstd compression, target columns are changed from TEXT to BLOB.
SQLite only supports ALTER TABLE ADD COLUMN, so a table rebuild is used.

Existing data compression is handled separately by scripts/db_compress_migrate.py
(this migration only changes schema types).

IMPORTANT: INSERT uses explicit column names to handle column order differences
between the original table (created incrementally) and the rebuilt table.
"""
import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_53(con: sqlite3.Connection) -> None:
    """Convert large text columns in analysis / file_annotations to BLOB type."""
    logger.info("  -> Migration 53: BLOB columns for analysis + file_annotations")

    # Rebuild analysis table with BLOB columns for compressible text fields.
    # Explicit column list required: column order in the original table differs
    # from the new DDL (description was added later via ALTER TABLE).
    con.execute("DROP TABLE IF EXISTS analysis_new")
    con.executescript("""
        CREATE TABLE analysis_new (
            id                  INTEGER PRIMARY KEY,
            file_id             INTEGER NOT NULL,
            engine              TEXT NOT NULL,
            analyzed_at         INTEGER NOT NULL,
            tags_json           TEXT,
            quality_score       REAL,
            quality_notes       BLOB,
            style               TEXT,
            composition         TEXT,
            mood                TEXT,
            color_palette_json  TEXT,
            prompt_suggestion   BLOB,
            raw_response        BLOB,
            description         TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
            UNIQUE(file_id, engine)
        );
    """)

    con.execute("""
        INSERT INTO analysis_new (
            id, file_id, engine, analyzed_at, tags_json, quality_score,
            quality_notes, style, composition, mood, color_palette_json,
            prompt_suggestion, raw_response, description
        )
        SELECT
            id, file_id, engine, analyzed_at, tags_json, quality_score,
            quality_notes, style, composition, mood, color_palette_json,
            prompt_suggestion, raw_response, description
        FROM analysis
    """)

    con.executescript("""
        DROP TABLE analysis;
        ALTER TABLE analysis_new RENAME TO analysis;
        CREATE INDEX IF NOT EXISTS idx_analysis_file_id     ON analysis(file_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_engine      ON analysis(engine);
        CREATE INDEX IF NOT EXISTS idx_analysis_analyzed_at ON analysis(analyzed_at);
        CREATE INDEX IF NOT EXISTS idx_analysis_style       ON analysis(style) WHERE style IS NOT NULL AND style != '';
    """)
    logger.info("     analysis rebuilt")

    # Rebuild file_annotations with value as BLOB.
    # Note: id is INTEGER PRIMARY KEY (no AUTOINCREMENT), FK has ON DELETE CASCADE.
    con.execute("DROP TABLE IF EXISTS file_annotations_new")
    con.executescript("""
        CREATE TABLE file_annotations_new (
            id          INTEGER PRIMARY KEY,
            file_id     INTEGER NOT NULL,
            source      TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       BLOB NOT NULL,
            confidence  REAL,
            created_at  INTEGER NOT NULL,
            UNIQUE(file_id, source, key),
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );
    """)

    con.execute("""
        INSERT INTO file_annotations_new (
            id, file_id, source, key, value, confidence, created_at
        )
        SELECT id, file_id, source, key, value, confidence, created_at
        FROM file_annotations
    """)

    con.executescript("""
        DROP TABLE file_annotations;
        ALTER TABLE file_annotations_new RENAME TO file_annotations;
        CREATE INDEX IF NOT EXISTS idx_annotations_file   ON file_annotations(file_id);
        CREATE INDEX IF NOT EXISTS idx_annotations_source ON file_annotations(source);
        CREATE INDEX IF NOT EXISTS idx_annotations_key    ON file_annotations(key);
    """)
    logger.info("     file_annotations rebuilt")

    set_schema_version(con, 53, "BLOB columns for zstd: analysis + file_annotations")
