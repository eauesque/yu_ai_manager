"""Migration 81: normalize file_wd_tags TEXT columns into dictionaries.

NOTE: at runtime ``con`` is a ``_MigrationConnectionProxy`` because the
registry wraps each migration in a SAVEPOINT/transaction. All DB calls MUST go
through this proxy; do NOT obtain a raw connection or the proxy's
executescript/commit guarding, which preserves savepoint isolation, is
bypassed. Annotated as sqlite3.Connection to match the established
migration-step convention.
"""

from __future__ import annotations

import logging
import sqlite3

from core.services_core.db_api import set_startup_status
from core.tagging.tag_normalize import normalize_tag

from .migration_errors import MigrationDataIntegrityError
from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50_000


def _create_dict_tables(con: sqlite3.Connection) -> None:
    # Proxied executescript keeps savepoint isolation.
    con.executescript("""
        CREATE TABLE IF NOT EXISTS wd_tag_dict (
            id                  INTEGER PRIMARY KEY,
            tag_name            TEXT NOT NULL UNIQUE,
            tag_name_normalized TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_wd_tag_dict_normalized
            ON wd_tag_dict(tag_name_normalized);
        CREATE TABLE IF NOT EXISTS wd_model_dict (
            id    INTEGER PRIMARY KEY,
            model TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS wd_category_dict (
            id       INTEGER PRIMARY KEY,
            category TEXT NOT NULL UNIQUE
        );
    """)


def _populate_dicts(con: sqlite3.Connection) -> None:
    con.execute(
        "INSERT OR IGNORE INTO wd_model_dict(model) "
        "SELECT DISTINCT model FROM file_wd_tags"
    )
    con.execute(
        "INSERT OR IGNORE INTO wd_category_dict(category) "
        "SELECT DISTINCT category FROM file_wd_tags"
    )
    tags = [row[0] for row in con.execute("SELECT DISTINCT tag_name FROM file_wd_tags")]
    con.executemany(
        "INSERT OR IGNORE INTO wd_tag_dict(tag_name, tag_name_normalized) "
        "VALUES(?, ?)",
        [(tag, normalize_tag(tag)) for tag in tags],
    )


def _create_new_table(con: sqlite3.Connection) -> None:
    con.execute("DROP TABLE IF EXISTS file_wd_tags_new")
    con.execute("""
        CREATE TABLE file_wd_tags_new (
            id          INTEGER PRIMARY KEY,
            file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            tag_id      INTEGER NOT NULL REFERENCES wd_tag_dict(id),
            confidence  REAL NOT NULL,
            category_id INTEGER NOT NULL REFERENCES wd_category_dict(id),
            model_id    INTEGER NOT NULL REFERENCES wd_model_dict(id),
            created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(file_id, tag_id, model_id)
        )
    """)


def _rebuild_file_wd_tags(con: sqlite3.Connection) -> None:
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM file_wd_tags").fetchone()[0]
    old_count = con.execute("SELECT COUNT(*) FROM file_wd_tags").fetchone()[0]
    processed = 0

    for start in range(0, max_id + 1, _BATCH_SIZE):
        end = start + _BATCH_SIZE
        con.execute(
            """
            INSERT INTO file_wd_tags_new
                (id, file_id, tag_id, confidence, category_id, model_id, created_at)
            SELECT f.id, f.file_id, td.id, f.confidence, cd.id, md.id, f.created_at
            FROM file_wd_tags f
            JOIN wd_tag_dict td ON td.tag_name = f.tag_name
            JOIN wd_category_dict cd ON cd.category = f.category
            JOIN wd_model_dict md ON md.model = f.model
            WHERE f.id > ? AND f.id <= ?
            """,
            (start, end),
        )
        processed = min(end, max_id)
        set_startup_status({
            "kind": "migration",
            "stage": "migrate_81_rebuild",
            "processed_id": processed,
            "max_id": max_id,
            "old_count": old_count,
        })


def _diagnose_missing_dicts(con: sqlite3.Connection) -> dict[str, int]:
    return {
        "tag": con.execute(
            "SELECT COUNT(*) FROM file_wd_tags f "
            "LEFT JOIN wd_tag_dict td ON td.tag_name=f.tag_name "
            "WHERE td.id IS NULL"
        ).fetchone()[0],
        "category": con.execute(
            "SELECT COUNT(*) FROM file_wd_tags f "
            "LEFT JOIN wd_category_dict cd ON cd.category=f.category "
            "WHERE cd.id IS NULL"
        ).fetchone()[0],
        "model": con.execute(
            "SELECT COUNT(*) FROM file_wd_tags f "
            "LEFT JOIN wd_model_dict md ON md.model=f.model "
            "WHERE md.id IS NULL"
        ).fetchone()[0],
    }


def _verify_rowcount(con: sqlite3.Connection) -> None:
    old_count = con.execute("SELECT COUNT(*) FROM file_wd_tags").fetchone()[0]
    new_count = con.execute("SELECT COUNT(*) FROM file_wd_tags_new").fetchone()[0]
    if old_count != new_count:
        diagnostics = _diagnose_missing_dicts(con)
        logger.error(
            "Migration 81 rowcount mismatch: old=%s new=%s missing=%s",
            old_count,
            new_count,
            diagnostics,
        )
        raise MigrationDataIntegrityError(
            "Migration 81 rowcount mismatch: "
            f"old={old_count}, new={new_count}, missing={diagnostics}"
        )


def _create_final_indexes(con: sqlite3.Connection) -> None:
    con.execute("CREATE INDEX IF NOT EXISTS idx_fwt_tag_id ON file_wd_tags(tag_id)")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_fwt_model_file "
        "ON file_wd_tags(model_id, file_id)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_wd_tag_dict_normalized "
        "ON wd_tag_dict(tag_name_normalized)"
    )


def _invalidate_stats_cache_if_present(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wd_tag_stats_cache' LIMIT 1"
    ).fetchone()
    if row is None:
        logger.info("Migration 81: wd_tag_stats_cache absent; skipping cache invalidation")
        return
    con.execute("UPDATE wd_tag_stats_cache SET stats_json='{}', computed_at=0")


def apply_migration_81(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 81: normalize file_wd_tags via dictionaries")

    if table_has_column(con, "file_wd_tags", "tag_id"):
        _create_dict_tables(con)
        _create_final_indexes(con)
        _invalidate_stats_cache_if_present(con)
        row = con.execute(
            "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (81,)
        ).fetchone()
        if row is None:
            set_schema_version(con, 81, "normalize file_wd_tags dictionaries")
        return

    _create_dict_tables(con)
    _populate_dicts(con)
    _create_new_table(con)
    _rebuild_file_wd_tags(con)
    _verify_rowcount(con)

    con.execute("DROP TABLE file_wd_tags")
    con.execute("ALTER TABLE file_wd_tags_new RENAME TO file_wd_tags")
    _create_final_indexes(con)
    _invalidate_stats_cache_if_present(con)

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (81,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 81, "normalize file_wd_tags dictionaries")
