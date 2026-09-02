"""Schema migration 47: github_issue_queue table.

Local queue for GitHub issues. Polled periodically by the scheduler,
pending issues are notified to MCP clients on connection.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_47(con: sqlite3.Connection) -> None:
    """Create github_issue_queue table."""
    logger.info("  -> Migration 47: github_issue_queue table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS github_issue_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            issue_number INTEGER NOT NULL,
            title TEXT,
            body TEXT,
            created_at TEXT,
            fetched_at TEXT,
            status TEXT DEFAULT 'pending',
            triage_result TEXT DEFAULT 'pending'
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_github_queue_status
        ON github_issue_queue (status)
    """)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_github_queue_repo_issue
        ON github_issue_queue (repo, issue_number)
    """)

    set_schema_version(con, 47, "github_issue_queue table")
