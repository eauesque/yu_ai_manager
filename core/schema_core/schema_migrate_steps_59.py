"""Migration 59: Peer pairing requests + tokens + peers.token columns."""
import logging

logger = logging.getLogger(__name__)
import contextlib

from .schema_migrate_version import set_schema_version


def apply_migration_59(con) -> None:
    logger.info("  -> Migration 59: peer pairing + tokens")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS peer_pairing_requests (
          request_id      TEXT PRIMARY KEY,
          peer_id         TEXT NOT NULL,
          host            TEXT NOT NULL,
          port            INTEGER NOT NULL,
          pin_hash        TEXT,
          pin_expires_at  INTEGER,
          verify_attempts INTEGER NOT NULL DEFAULT 0,
          status          TEXT NOT NULL,
          created_at      INTEGER NOT NULL,
          updated_at      INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pairing_status
          ON peer_pairing_requests(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_pairing_peer_id
          ON peer_pairing_requests(peer_id, status);

        CREATE TABLE IF NOT EXISTS peer_tokens (
          peer_id    TEXT PRIMARY KEY,
          token_hash TEXT NOT NULL,
          issued_at  INTEGER NOT NULL,
          expires_at INTEGER NOT NULL,
          revoked_at INTEGER,
          source     TEXT NOT NULL DEFAULT 'pairing',
          note       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_peer_tokens_expires
          ON peer_tokens(expires_at) WHERE revoked_at IS NULL;

        CREATE TABLE IF NOT EXISTS peers (
          peer_id           TEXT PRIMARY KEY,
          name              TEXT,
          api_host          TEXT,
          api_port          INTEGER,
          token             TEXT,
          token_expires_at  INTEGER,
          token_issued_at   INTEGER,
          allow_legacy_auth INTEGER NOT NULL DEFAULT 0,
          created_at        INTEGER NOT NULL,
          updated_at        INTEGER NOT NULL
        );
    """)
    # If peers existed from an earlier prototype, ensure new columns are present.
    for _col, ddl in [
        ("token", "ALTER TABLE peers ADD COLUMN token TEXT"),
        ("token_expires_at", "ALTER TABLE peers ADD COLUMN token_expires_at INTEGER"),
        ("token_issued_at", "ALTER TABLE peers ADD COLUMN token_issued_at INTEGER"),
        ("allow_legacy_auth", "ALTER TABLE peers ADD COLUMN allow_legacy_auth INTEGER NOT NULL DEFAULT 0"),
    ]:
        with contextlib.suppress(Exception):
            con.execute(ddl)
    set_schema_version(con, 59, "Peer pairing requests + tokens + peers token columns")
