"""Schema migration steps for legacy tagdb DB."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .tagdb_db_schema_common import table_has_column
from .tagdb_db_schema_migrate_version import set_schema_version


def apply_migration_1(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 1: Adding model tracking columns")
    if not table_has_column(con, "templates", "model_name"):
        con.execute("ALTER TABLE templates ADD COLUMN model_name TEXT")
    if not table_has_column(con, "templates", "model_hash"):
        con.execute("ALTER TABLE templates ADD COLUMN model_hash TEXT")
    set_schema_version(con, 1, "Add model_name and model_hash to templates")
    logger.info("     [OK] Model tracking enabled")


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
    logger.info("     [OK] ZIP support enabled")
    logger.info("     [OK] Parser version tracking enabled")


def apply_migration_3(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 3: Adding image dimensions columns")
    if not table_has_column(con, "files", "width"):
        con.execute("ALTER TABLE files ADD COLUMN width INTEGER")
    if not table_has_column(con, "files", "height"):
        con.execute("ALTER TABLE files ADD COLUMN height INTEGER")
    set_schema_version(con, 3, "Add width/height columns to files")
    logger.info("     [OK] Image dimensions enabled")


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
    logger.info("     [OK] Media metadata state tracking enabled")


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
    logger.info("     [OK] Cache index enabled")
