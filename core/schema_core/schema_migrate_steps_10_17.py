"""Schema migration steps 10-17."""

import logging
import sqlite3

from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_10(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 10: Adding query_json to collections for smart collections")
    if not table_has_column(con, "collections", "query_json"):
        con.execute("ALTER TABLE collections ADD COLUMN query_json TEXT")
    set_schema_version(con, 10, "Add query_json to collections for smart collections")


def apply_migration_11(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 11: Adding webhook_deliveries table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status_code INTEGER,
            response_body TEXT,
            attempt INTEGER NOT NULL DEFAULT 1,
            success INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at INTEGER NOT NULL,
            delivered_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_wh_del_webhook_id ON webhook_deliveries(webhook_id);
        CREATE INDEX IF NOT EXISTS idx_wh_del_created_at ON webhook_deliveries(created_at);
        """
    )
    set_schema_version(con, 11, "Add webhook_deliveries for webhook delivery logging")


def apply_migration_12(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 12: Adding file_ratings table and phash column")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS file_ratings (
          file_id INTEGER PRIMARY KEY,
          rating  INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
          rated_at   INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_file_ratings_rating ON file_ratings(rating);
        """
    )
    if not table_has_column(con, "files", "phash"):
        con.execute("ALTER TABLE files ADD COLUMN phash TEXT")
    set_schema_version(con, 12, "Add file_ratings table and phash column")


def apply_migration_13(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 13: Adding file_annotations table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS file_annotations (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL,
            created_at INTEGER NOT NULL,
            UNIQUE(file_id, source, key),
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_annotations_file ON file_annotations(file_id);
        CREATE INDEX IF NOT EXISTS idx_annotations_source ON file_annotations(source);
        CREATE INDEX IF NOT EXISTS idx_annotations_key ON file_annotations(key);
        """
    )
    set_schema_version(con, 13, "Add file_annotations table for AI/agent annotations")


def apply_migration_14(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 14: Adding file_wd_tags table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS file_wd_tags (
            id         INTEGER PRIMARY KEY,
            file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            tag_name   TEXT NOT NULL,
            confidence REAL NOT NULL,
            category   TEXT NOT NULL DEFAULT 'general',
            model      TEXT NOT NULL,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(file_id, tag_name, model)
        );
        CREATE INDEX IF NOT EXISTS idx_fwt_file ON file_wd_tags(file_id);
        """
    )
    if table_has_column(con, "file_wd_tags", "tag_name"):
        con.execute("CREATE INDEX IF NOT EXISTS idx_fwt_tag ON file_wd_tags(tag_name)")
    if table_has_column(con, "file_wd_tags", "category"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_fwt_category ON file_wd_tags(category)"
        )
    set_schema_version(con, 14, "Add file_wd_tags table for WD-Tagger auto-tagging")


def apply_migration_15(con: sqlite3.Connection) -> None:
    import re

    logger.info("  -> Migration 15: Backfilling model_name from A1111 Parameters")
    re_model = re.compile(r",\s*Model:\s*([^,\n]+)")
    re_hash = re.compile(r",\s*Model hash:\s*([^,\n]+)")
    rows = con.execute(
        "SELECT id, raw_prompt FROM templates "
        "WHERE model_name IS NULL AND raw_prompt IS NOT NULL "
        "AND raw_prompt LIKE '%Steps:%' AND raw_prompt LIKE '%Model: %'"
    ).fetchall()

    count = 0
    for template_id, raw_prompt in rows:
        params_section = raw_prompt[raw_prompt.rfind("Steps:"):]
        model_match = re_model.search(params_section)
        if not model_match:
            continue
        model_name = model_match.group(1).strip()
        if not model_name:
            continue
        hash_match = re_hash.search(params_section)
        model_hash = hash_match.group(1).strip() or None if hash_match else None
        con.execute(
            "UPDATE templates SET model_name=?, model_hash=? WHERE id=?",
            (model_name, model_hash, template_id),
        )
        count += 1

    logger.info("     Backfilled %d model names from A1111 Parameters", count)
    from core.paths import get_cache_dir
    for cache_file in get_cache_dir().glob("*_cache.json"):
        cache_file.unlink(missing_ok=True)
    set_schema_version(con, 15, "Backfill model_name from A1111 Parameters text")


def apply_migration_16(con: sqlite3.Connection) -> None:
    import datetime as _dt

    logger.info("  -> Migration 16: Correcting UTC timezone offset in ZIP/7z mtime")
    offset = _dt.datetime.now(_dt.UTC).astimezone().utcoffset()
    offset_seconds = int(offset.total_seconds()) if offset else 0
    if offset_seconds == 0:
        logger.info("     Local timezone is UTC -- no correction needed")
        set_schema_version(con, 16, "UTC mtime correction (no-op: UTC locale)")
        return

    # is_deleted / is_zip_member were not in very old DBs; skip correction if absent
    if not table_has_column(con, "files", "is_deleted") or not table_has_column(con, "files", "is_zip_member"):
        logger.info("     files.is_deleted/is_zip_member absent -- skipping UTC correction")
        set_schema_version(con, 16, "UTC mtime correction (no-op: old schema)")
        return

    nai_sources = (
        "'novelai_v4_png','novelai_v4_webp','novelai_v4',"
        "'novelai_png','novelai_webp','nai_webp'"
    )
    affected = con.execute(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND is_zip_member=1 "
        f"AND meta_source IN ({nai_sources})"
    ).fetchone()[0]
    if affected == 0:
        logger.info("     No affected NAI ZIP members found")
        set_schema_version(con, 16, "UTC mtime correction (0 files)")
        return

    logger.info("     Correcting %d records (UTC offset: +%ds = +%dh)", affected, offset_seconds, offset_seconds // 3600)
    con.execute(
        "UPDATE files SET mtime = mtime + ? "
        "WHERE is_deleted=0 AND is_zip_member=1 "
        f"AND meta_source IN ({nai_sources})",
        (offset_seconds,),
    )
    set_schema_version(con, 16, f"UTC mtime correction ({affected} files, offset +{offset_seconds}s)")


def apply_migration_17(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 17: Merging duplicate tags rows")
    dup_groups = con.execute(
        "SELECT tag, namespace, MIN(id) AS keep_id, GROUP_CONCAT(id) AS all_ids "
        "FROM tags GROUP BY tag, namespace HAVING COUNT(*) > 1"
    ).fetchall()
    merged_tags = 0
    merged_file_tags = 0

    for _tag, _namespace, keep_id, all_ids_str in dup_groups:
        dup_ids = [int(x) for x in all_ids_str.split(",") if int(x) != keep_id]
        for dup_id in dup_ids:
            merged_file_tags += con.execute(
                "UPDATE file_tags SET tag_id = ? WHERE tag_id = ? "
                "AND NOT EXISTS (SELECT 1 FROM file_tags ft2 "
                "WHERE ft2.file_id = file_tags.file_id AND ft2.tag_id = ?)",
                (keep_id, dup_id, keep_id),
            ).rowcount
            con.execute("DELETE FROM file_tags WHERE tag_id = ?", (dup_id,))
            con.execute("DELETE FROM tags WHERE id = ?", (dup_id,))
            merged_tags += 1

    orphan_count = con.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM file_tags)"
    ).rowcount
    total_removed = merged_tags + orphan_count
    logger.info("     Merged %d duplicate tag rows (%d file_tags re-pointed)", merged_tags, merged_file_tags)
    if orphan_count > 0:
        logger.info("     Cleaned %d orphan tags", orphan_count)
    logger.info("     Total tags removed: %d", total_removed)
    set_schema_version(con, 17, f"Merge duplicate tags ({total_removed} removed)")
