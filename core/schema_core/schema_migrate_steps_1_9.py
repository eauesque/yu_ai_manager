"""Schema migration steps 1-9."""

import logging
import sqlite3

from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_1(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 1: Adding model tracking columns")
    if not table_has_column(con, "templates", "model_name"):
        con.execute("ALTER TABLE templates ADD COLUMN model_name TEXT")
    if not table_has_column(con, "templates", "model_hash"):
        con.execute("ALTER TABLE templates ADD COLUMN model_hash TEXT")
    set_schema_version(con, 1, "Add model_name and model_hash to templates")


def apply_migration_2(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 2: Adding ZIP tracking columns")
    if not table_has_column(con, "files", "is_zip_member"):
        con.execute("ALTER TABLE files ADD COLUMN is_zip_member INTEGER NOT NULL DEFAULT 0")
        con.execute("ALTER TABLE files ADD COLUMN extracted_from_zip TEXT")
        con.execute("ALTER TABLE files ADD COLUMN extracted_from_internal TEXT")
        con.execute("ALTER TABLE files ADD COLUMN extraction_date INTEGER")
        con.execute("ALTER TABLE files ADD COLUMN extracted_to_file_id INTEGER")
    if not table_has_column(con, "files", "parser_version"):
        con.execute("ALTER TABLE files ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 1")
    set_schema_version(con, 2, "Add ZIP tracking and parser_version to files")


def apply_migration_3(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 3: Adding width/height columns to files")
    if not table_has_column(con, "files", "width"):
        con.execute("ALTER TABLE files ADD COLUMN width INTEGER")
    if not table_has_column(con, "files", "height"):
        con.execute("ALTER TABLE files ADD COLUMN height INTEGER")
    con.execute("CREATE INDEX IF NOT EXISTS idx_files_width ON files(width) WHERE width IS NOT NULL")
    con.execute("CREATE INDEX IF NOT EXISTS idx_files_height ON files(height) WHERE height IS NOT NULL")
    set_schema_version(con, 3, "Add width/height to files for resolution filter")


def apply_migration_4(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 4: Adding media_extract_state table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS media_extract_state (
          file_id INTEGER PRIMARY KEY,
          cache_state TEXT NOT NULL DEFAULT 'none',
          metadata_schema_version INTEGER,
          metadata_extracted_at INTEGER,
          metadata_source TEXT,
          metadata_source_version TEXT,
          fingerprint_mtime INTEGER,
          fingerprint_size INTEGER,
          fingerprint_hash TEXT,
          error_code TEXT,
          error_at INTEGER,
          error_count INTEGER NOT NULL DEFAULT 0,
          next_retry_after INTEGER,
          last_access_at INTEGER,
          updated_at INTEGER NOT NULL,
          FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_media_extract_cache_state ON media_extract_state(cache_state);
        CREATE INDEX IF NOT EXISTS idx_media_extract_next_retry ON media_extract_state(next_retry_after);
        CREATE INDEX IF NOT EXISTS idx_media_extract_last_access ON media_extract_state(last_access_at);
        """
    )
    set_schema_version(con, 4, "Add media_extract_state for read-only media metadata cache lifecycle")


def apply_migration_5(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 5: Adding cache_entry table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS cache_entry (
          cache_key TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          path TEXT NOT NULL,
          file_id INTEGER,
          size_bytes INTEGER NOT NULL DEFAULT 0,
          last_access_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cache_entry_kind_last_access ON cache_entry(kind, last_access_at);
        """
    )
    set_schema_version(con, 5, "Add cache_entry for atime-independent L2 cache eviction")


def apply_migration_6(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 6: Adding favorites table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS favorites (
          file_id INTEGER PRIMARY KEY,
          added_at INTEGER NOT NULL,
          FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        """
    )
    set_schema_version(con, 6, "Add favorites table for bookmark feature")


def apply_migration_7(con: sqlite3.Connection) -> None:
    import time

    logger.info("  -> Migration 7: Adding collections table and extending favorites")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS collections (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL
        );
        """
    )
    existing = con.execute("SELECT id FROM collections WHERE id=1").fetchone()
    if not existing:
        con.execute(
            "INSERT INTO collections (id, name, sort_order, created_at) VALUES (1, 'Favorites', 0, ?)",
            (int(time.time()),),
        )
    if not table_has_column(con, "favorites", "collection_id"):
        con.execute("ALTER TABLE favorites ADD COLUMN collection_id INTEGER NOT NULL DEFAULT 1")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_fav_file_collection ON favorites(file_id, collection_id)")
    set_schema_version(con, 7, "Add collections table and collection_id to favorites")


def apply_migration_8(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 8: Rebuild favorites with compound primary key")
    # Drop FTS triggers before DROP/RENAME so SQLite schema rebuild doesn't
    # validate stale triggers that may reference columns not yet added.
    # Migrations 29 and 52 will recreate these triggers correctly.
    for trig in ("templates_ai", "templates_ad", "templates_au"):
        con.execute(f"DROP TRIGGER IF EXISTS {trig}")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS favorites_new (
          file_id INTEGER NOT NULL,
          collection_id INTEGER NOT NULL DEFAULT 1,
          added_at INTEGER NOT NULL,
          PRIMARY KEY (file_id, collection_id),
          FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        INSERT OR IGNORE INTO favorites_new (file_id, collection_id, added_at)
          SELECT file_id, collection_id, added_at FROM favorites;
        DROP TABLE favorites;
        ALTER TABLE favorites_new RENAME TO favorites;
        """
    )
    set_schema_version(con, 8, "Rebuild favorites with compound PK (file_id, collection_id)")


def apply_migration_9(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 9: Adding analysis table")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            engine TEXT NOT NULL,
            analyzed_at INTEGER NOT NULL,
            tags_json TEXT,
            quality_score REAL,
            quality_notes TEXT,
            style TEXT,
            composition TEXT,
            mood TEXT,
            color_palette_json TEXT,
            prompt_suggestion TEXT,
            raw_response TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
            UNIQUE(file_id, engine)
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_file_id ON analysis(file_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_engine ON analysis(engine);
        CREATE INDEX IF NOT EXISTS idx_analysis_analyzed_at ON analysis(analyzed_at);
        """
    )
    set_schema_version(con, 9, "Add analysis table for AI image analysis results")
