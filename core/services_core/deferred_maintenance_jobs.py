"""Persistent queue for heavy DB maintenance jobs deferred out of migrations."""

import sqlite3
import time
from typing import Any


def ensure_deferred_jobs_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS deferred_maintenance_jobs (
            id INTEGER PRIMARY KEY,
            job_key TEXT NOT NULL UNIQUE,
            task TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_deferred_jobs_status "
        "ON deferred_maintenance_jobs(status, updated_at)"
    )


def enqueue_deferred_job(
    con: sqlite3.Connection,
    job_key: str,
    task: str,
    payload_json: str = "{}",
) -> None:
    now = int(time.time())
    ensure_deferred_jobs_table(con)
    con.execute(
        """
        INSERT INTO deferred_maintenance_jobs(
            job_key, task, payload_json, status, created_at, updated_at
        )
        VALUES (?, ?, ?, 'pending', ?, ?)
        ON CONFLICT(job_key) DO UPDATE SET
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        WHERE deferred_maintenance_jobs.status != 'done'
        """,
        (job_key, task, payload_json, now, now),
    )


def claim_next_deferred_job(con: sqlite3.Connection) -> dict[str, Any] | None:
    ensure_deferred_jobs_table(con)
    previous_row_factory = con.row_factory
    try:
        con.row_factory = sqlite3.Row
        row = con.execute(
            """
            SELECT id, job_key, task, payload_json
            FROM deferred_maintenance_jobs
            WHERE status='pending'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
    finally:
        con.row_factory = previous_row_factory

    if row is None:
        return None

    now = int(time.time())
    cur = con.execute(
        """
        UPDATE deferred_maintenance_jobs
        SET status='running', attempts=attempts+1, updated_at=?
        WHERE id=? AND status='pending'
        """,
        (now, row["id"]),
    )
    if cur.rowcount == 0:
        return None
    return dict(row)


def mark_deferred_job_done(con: sqlite3.Connection, job_id: int) -> None:
    con.execute(
        """
        UPDATE deferred_maintenance_jobs
        SET status='done', updated_at=?, error_message=NULL
        WHERE id=?
        """,
        (int(time.time()), job_id),
    )
