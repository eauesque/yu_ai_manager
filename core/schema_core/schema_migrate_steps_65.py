"""Migration 65: search aggregate stats for count-heavy filters."""

import logging
import time

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _create_search_stats_schema(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS file_tag_counts (
            file_id INTEGER PRIMARY KEY,
            tag_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS search_stats (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_file_tag_counts_tag_count "
        "ON file_tag_counts(tag_count)"
    )


def _populate_search_stats(con) -> None:
    now = int(time.time())
    con.execute("DELETE FROM file_tag_counts")
    con.execute("""
        INSERT INTO file_tag_counts(file_id, tag_count)
        SELECT file_id, COUNT(*)
        FROM file_tags
        GROUP BY file_id
    """)
    con.execute("""
        INSERT OR REPLACE INTO search_stats(key, value, updated_at)
        VALUES (
            'active_tagged_files',
            (
                SELECT COUNT(*)
                FROM file_tag_counts c
                JOIN files f ON f.id=c.file_id
                WHERE c.tag_count > 0 AND f.is_deleted=0
            ),
            ?
        )
    """, (now,))
    con.execute("""
        INSERT OR REPLACE INTO search_stats(key, value, updated_at)
        VALUES (
            'active_files',
            (SELECT COUNT(*) FROM files WHERE is_deleted=0),
            ?
        )
    """, (now,))


def _create_search_stats_triggers(con) -> None:
    con.executescript("""
        DROP TRIGGER IF EXISTS trg_file_tags_ai_search_stats;
        DROP TRIGGER IF EXISTS trg_file_tags_ad_search_stats;
        DROP TRIGGER IF EXISTS trg_files_ai_search_stats;
        DROP TRIGGER IF EXISTS trg_files_au_deleted_search_stats;
        DROP TRIGGER IF EXISTS trg_files_ad_search_stats;

        CREATE TRIGGER trg_file_tags_ai_search_stats
        AFTER INSERT ON file_tags
        BEGIN
            UPDATE search_stats
            SET value = value + 1, updated_at = strftime('%s','now')
            WHERE key='active_tagged_files'
              AND COALESCE((SELECT is_deleted FROM files WHERE id=NEW.file_id), 1)=0
              AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=NEW.file_id), 0)=0;

            INSERT INTO file_tag_counts(file_id, tag_count)
            VALUES (NEW.file_id, 1)
            ON CONFLICT(file_id) DO UPDATE SET tag_count = tag_count + 1;
        END;

        CREATE TRIGGER trg_file_tags_ad_search_stats
        AFTER DELETE ON file_tags
        BEGIN
            UPDATE search_stats
            SET value = value - 1, updated_at = strftime('%s','now')
            WHERE key='active_tagged_files'
              AND COALESCE((SELECT is_deleted FROM files WHERE id=OLD.file_id), 1)=0
              AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=OLD.file_id), 0)=1;

            UPDATE file_tag_counts
            SET tag_count = tag_count - 1
            WHERE file_id=OLD.file_id;

            DELETE FROM file_tag_counts
            WHERE file_id=OLD.file_id AND tag_count <= 0;
        END;

        CREATE TRIGGER trg_files_ai_search_stats
        AFTER INSERT ON files
        BEGIN
            UPDATE search_stats
            SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE 0 END,
                updated_at = strftime('%s','now')
            WHERE key='active_files';
        END;

        CREATE TRIGGER trg_files_au_deleted_search_stats
        AFTER UPDATE OF is_deleted ON files
        WHEN OLD.is_deleted != NEW.is_deleted
        BEGIN
            UPDATE search_stats
            SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE -1 END,
                updated_at = strftime('%s','now')
            WHERE key='active_files';

            UPDATE search_stats
            SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE -1 END,
                updated_at = strftime('%s','now')
            WHERE key='active_tagged_files'
              AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=NEW.id), 0) > 0;
        END;

        CREATE TRIGGER trg_files_ad_search_stats
        AFTER DELETE ON files
        BEGIN
            UPDATE search_stats
            SET value = value - CASE WHEN OLD.is_deleted=0 THEN 1 ELSE 0 END,
                updated_at = strftime('%s','now')
            WHERE key='active_files';

            UPDATE search_stats
            SET value = value - CASE
                    WHEN OLD.is_deleted=0
                     AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=OLD.id), 0) > 0
                    THEN 1 ELSE 0 END,
                updated_at = strftime('%s','now')
            WHERE key='active_tagged_files';

            DELETE FROM file_tag_counts WHERE file_id=OLD.id;
        END;
    """)


def apply_migration_65(con) -> None:
    logger.info("  -> Migration 65: search aggregate stats")
    _create_search_stats_schema(con)
    _populate_search_stats(con)
    _create_search_stats_triggers(con)
    set_schema_version(con, 65, "Search aggregate stats for count-heavy filters")
