"""Database operations for Hailo Remote Tagger tags.

CRUD operations on the file_hailo_tags table.
Uses parameterized SQL throughout.
"""

from __future__ import annotations

import logging
import time

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)


def ensure_table(con) -> None:
    """Create file_hailo_tags table if it does not exist (runtime fallback)."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS file_hailo_tags (
            id         INTEGER PRIMARY KEY,
            file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            tag_name   TEXT NOT NULL,
            confidence REAL NOT NULL,
            source     TEXT NOT NULL DEFAULT 'hailo_remote',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(file_id, tag_name)
        );
        CREATE INDEX IF NOT EXISTS idx_fht_file ON file_hailo_tags(file_id);
        CREATE INDEX IF NOT EXISTS idx_fht_tag  ON file_hailo_tags(tag_name);
    """)


def save_hailo_tags(file_id: int, tags: list[dict]) -> int:
    """Save Hailo tag predictions to database (UPSERT).

    Args:
        file_id: Database file ID
        tags: List of {"tag": str, "confidence": float}

    Returns number of tags saved.
    """
    def _write() -> int:
        con = get_db()
        now = int(time.time())
        params = [
            (file_id, t["tag"], t["confidence"], "hailo_remote", now)
            for t in tags
        ]
        if params:
            con.executemany(
                """INSERT INTO file_hailo_tags (file_id, tag_name, confidence, source, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(file_id, tag_name) DO UPDATE SET
                     confidence = excluded.confidence,
                     source     = excluded.source,
                     created_at = excluded.created_at""",
                params,
            )
        con.commit()
        return len(params)

    return submit_db_write(_write)


def get_hailo_tags(file_id: int) -> list[dict]:
    """Get Hailo tags for a file, ordered by confidence descending."""
    con = get_readonly_db()
    rows = con.execute(
        """SELECT tag_name, confidence, source, created_at
           FROM file_hailo_tags WHERE file_id = ?
           ORDER BY confidence DESC, tag_name ASC""",
        (file_id,),
    )
    return [dict(r) for r in rows]


def delete_hailo_tags(file_id: int) -> int:
    """Delete Hailo tags for a file. Returns count of deleted rows."""
    def _write() -> int:
        con = get_db()
        cur = con.execute(
            "DELETE FROM file_hailo_tags WHERE file_id = ?",
            (file_id,),
        )
        con.commit()
        return cur.rowcount

    return submit_db_write(_write)


def count_untagged_files(limit: int = 0) -> int:
    """Count files that have no Hailo tags."""
    con = get_readonly_db()
    row = con.execute(
        """SELECT COUNT(*)
           FROM files f
           WHERE f.is_deleted = 0
             AND NOT EXISTS (
               SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id
             )"""
    ).fetchone()
    return row[0]


def get_untagged_files(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get files that have no Hailo tags.

    Returns list of {id, path, meta_source}.
    """
    con = get_readonly_db()
    rows = con.execute(
        """SELECT f.id, f.path, f.meta_source
           FROM files f
           WHERE f.is_deleted = 0
             AND NOT EXISTS (
               SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id
             )
           ORDER BY f.id
           LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    return [dict(r) for r in rows]
