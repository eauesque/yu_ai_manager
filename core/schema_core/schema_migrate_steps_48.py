"""Schema migration 48: bluesky_notification_queue table.

Local queue for Bluesky notifications (mentions, replies, quotes,
follows, likes, reposts). Polled periodically by the scheduler.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_48(con: sqlite3.Connection) -> None:
    """Create bluesky_notification_queue table."""
    logger.info("  -> Migration 48: bluesky_notification_queue table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS bluesky_notification_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT NOT NULL,
            author_handle TEXT NOT NULL,
            author_display_name TEXT,
            uri TEXT NOT NULL,
            cid TEXT,
            subject_uri TEXT,
            text TEXT,
            indexed_at TEXT,
            fetched_at TEXT,
            status TEXT DEFAULT 'pending',
            triage_result TEXT DEFAULT 'pending',
            auto_response_sent INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_bsky_queue_status
        ON bluesky_notification_queue (status)
    """)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_bsky_queue_uri
        ON bluesky_notification_queue (uri)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_bsky_queue_type
        ON bluesky_notification_queue (notification_type)
    """)

    set_schema_version(con, 48, "bluesky_notification_queue table")
