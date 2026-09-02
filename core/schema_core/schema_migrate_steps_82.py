"""Migration 82: scale file_wd_tags.confidence REAL to confidence_milli INTEGER."""

from __future__ import annotations

import logging
import sqlite3

from core.services_core.db_api import set_startup_status

from .migration_errors import MigrationDataIntegrityError
from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50_000


def _create_new_table(con: sqlite3.Connection) -> None:
    con.execute("DROP TABLE IF EXISTS file_wd_tags_new")
    con.execute("""
        CREATE TABLE file_wd_tags_new (
            id               INTEGER PRIMARY KEY,
            file_id          INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            tag_id           INTEGER NOT NULL REFERENCES wd_tag_dict(id),
            confidence_milli INTEGER NOT NULL CHECK(confidence_milli BETWEEN 0 AND 1000),
            category_id      INTEGER NOT NULL REFERENCES wd_category_dict(id),
            model_id         INTEGER NOT NULL REFERENCES wd_model_dict(id),
            created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(file_id, tag_id, model_id)
        )
    """)


def _rebuild_file_wd_tags(con: sqlite3.Connection) -> None:
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM file_wd_tags").fetchone()[0]
    old_count = con.execute("SELECT COUNT(*) FROM file_wd_tags").fetchone()[0]

    for start in range(0, max_id + 1, _BATCH_SIZE):
        end = start + _BATCH_SIZE
        con.execute(
            """
            INSERT INTO file_wd_tags_new
                (id, file_id, tag_id, confidence_milli, category_id, model_id, created_at)
            SELECT id, file_id, tag_id, CAST(round(confidence * 1000) AS INTEGER),
                   category_id, model_id, created_at
            FROM file_wd_tags
            WHERE id > ? AND id <= ?
            """,
            (start, end),
        )
        set_startup_status({
            "kind": "migration",
            "stage": "migrate_82_rebuild",
            "processed_id": min(end, max_id),
            "max_id": max_id,
            "old_count": old_count,
        })


def _verify_rowcount(con: sqlite3.Connection) -> None:
    old_count = con.execute("SELECT COUNT(*) FROM file_wd_tags").fetchone()[0]
    new_count = con.execute("SELECT COUNT(*) FROM file_wd_tags_new").fetchone()[0]
    if old_count != new_count:
        logger.error("Migration 82 rowcount mismatch: old=%s new=%s", old_count, new_count)
        raise MigrationDataIntegrityError(
            f"Migration 82 rowcount mismatch: old={old_count}, new={new_count}"
        )


def _create_final_indexes(con: sqlite3.Connection) -> None:
    con.execute("CREATE INDEX IF NOT EXISTS idx_fwt_tag_id ON file_wd_tags(tag_id)")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_fwt_model_file "
        "ON file_wd_tags(model_id, file_id)"
    )


def _invalidate_stats_cache_if_present(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wd_tag_stats_cache' LIMIT 1"
    ).fetchone()
    if row is None:
        logger.info("Migration 82: wd_tag_stats_cache absent; skipping cache invalidation")
        return
    con.execute("UPDATE wd_tag_stats_cache SET stats_json='{}', computed_at=0")


def apply_migration_82(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 82: scale file_wd_tags confidence to INTEGER milli")

    if table_has_column(con, "file_wd_tags", "confidence_milli"):
        _create_final_indexes(con)
        _invalidate_stats_cache_if_present(con)
        row = con.execute(
            "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (82,)
        ).fetchone()
        if row is None:
            set_schema_version(
                con, 82, "scale file_wd_tags confidence to milli integer"
            )
        return

    _create_new_table(con)
    _rebuild_file_wd_tags(con)
    _verify_rowcount(con)

    con.execute("DROP TABLE file_wd_tags")
    con.execute("ALTER TABLE file_wd_tags_new RENAME TO file_wd_tags")
    _create_final_indexes(con)
    _invalidate_stats_cache_if_present(con)

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (82,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 82, "scale file_wd_tags confidence to milli integer")
