"""Migration 70: normalized AI annotation and embedding result tables."""

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _set_schema_version_once(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1",
        (70,),
    ).fetchone()
    if row is None:
        set_schema_version(con, 70, "Normalized AI annotation and embedding tables")


def apply_migration_70(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 70: image_ai_annotations + image_embeddings")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS image_ai_annotations (
            id INTEGER PRIMARY KEY,
            image_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL DEFAULT '',
            result_json TEXT NOT NULL,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'done',
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(image_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_image_ai_annotations_image_id
            ON image_ai_annotations(image_id);

        CREATE INDEX IF NOT EXISTS idx_image_ai_annotations_task_model
            ON image_ai_annotations(task, model_name, model_version);

        CREATE TABLE IF NOT EXISTS image_embeddings (
            image_id INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL DEFAULT '',
            dim INTEGER NOT NULL,
            vector_blob BLOB NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (image_id, model_name, model_version),
            FOREIGN KEY(image_id) REFERENCES files(id) ON DELETE CASCADE
        );
        """
    )
    _set_schema_version_once(con)
