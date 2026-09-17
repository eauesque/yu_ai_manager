"""Migration 58: Remote import tables and imported_from_peer column."""
import contextlib
import logging

logger = logging.getLogger(__name__)
from .schema_migrate_version import set_schema_version


def apply_migration_58(con) -> None:
    logger.info("  -> Migration 58: remote import tables")
    with contextlib.suppress(Exception):  # column may already exist
        con.execute("ALTER TABLE files ADD COLUMN imported_from_peer TEXT")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS import_session (
          id                   TEXT PRIMARY KEY,
          peer_id              TEXT NOT NULL,
          peer_name            TEXT NOT NULL,
          mode                 TEXT NOT NULL,
          status               TEXT NOT NULL DEFAULT 'pending',
          last_seen_rowid      INTEGER,
          snapshot_max_rowid   INTEGER,
          total_files          INTEGER,
          done_files           INTEGER NOT NULL DEFAULT 0,
          import_folder        TEXT NOT NULL,
          options              TEXT NOT NULL DEFAULT '{"include_favorites":false,"merge_metadata":false}',
          created_at           INTEGER NOT NULL,
          updated_at           INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_file_id_map (
          session_id     TEXT NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
          remote_peer_id TEXT NOT NULL,
          remote_file_id INTEGER NOT NULL,
          local_file_id  INTEGER NOT NULL,
          status         TEXT NOT NULL DEFAULT 'done',
          PRIMARY KEY (session_id, remote_peer_id, remote_file_id)
        );

        CREATE TABLE IF NOT EXISTS import_collection_id_map (
          session_id            TEXT NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
          remote_peer_id        TEXT NOT NULL,
          remote_collection_id  INTEGER NOT NULL,
          local_collection_id   INTEGER NOT NULL,
          PRIMARY KEY (session_id, remote_peer_id, remote_collection_id)
        );
    """)
    set_schema_version(con, 58, "Remote import tables")
