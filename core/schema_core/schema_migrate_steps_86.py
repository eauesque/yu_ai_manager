"""Schema migration 86: persist mesh inference eligibility.

``inference_types`` mirrors discovered peer capabilities. Disabled types remain
separate because mDNS re-discovery may replace a peer row without re-enabling a
user-disabled inference type.
"""

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_86(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 86: persist mesh inference eligibility")

    columns = {row[1] for row in con.execute("PRAGMA table_info(peers)")}
    if "inference_types" not in columns:
        con.execute("ALTER TABLE peers ADD COLUMN inference_types TEXT NOT NULL DEFAULT '[]'")
    con.execute("""
        CREATE TABLE IF NOT EXISTS peer_inference_disabled (
            peer_id        TEXT NOT NULL,
            inference_type TEXT NOT NULL,
            PRIMARY KEY (peer_id, inference_type)
        )
    """)

    # Do NOT call con.commit() here — schema_migrate_registry manages transactions.
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (86,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 86, "persist mesh inference eligibility")
