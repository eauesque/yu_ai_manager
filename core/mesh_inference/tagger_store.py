"""Database operations for mesh-based tagger results.

Writes to the existing file_hailo_tags table. Migrated from
core/tagger_servers_core/store.py with source default changed to "mesh".

Source format examples:
  - "mesh:<peer_name>"   -- mesh peer (local or remote)
  - "mesh"               -- generic mesh source (fallback)
"""

from __future__ import annotations

import logging
import time

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)


def _save_tagger_tags_with_connection(
    con,
    file_id: int,
    tags: list[dict],
    source: str,
) -> int:
    now = int(time.time())
    params = [
        (file_id, t["tag"], t["confidence"], source, now)
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
    return len(params)


def save_tagger_tags(
    file_id: int,
    tags: list[dict],
    source: str = "mesh",
) -> int:
    """Save tagger predictions to file_hailo_tags (UPSERT).

    Args:
        file_id: Database file ID
        tags: List of {"tag": str, "confidence": float}
        source: Worker source identifier (e.g. "mesh:pi-a")

    Returns number of tags saved.
    """
    return save_tagger_tags_batch([(file_id, tags, source)])


def save_tagger_tags_batch(items: list[tuple[int, list[dict], str]]) -> int:
    """Save tagger results for multiple files in one serialized writer transaction."""
    if not items:
        return 0

    def _write() -> int:
        con = get_db()
        total = 0
        for file_id, tags, source in items:
            total += _save_tagger_tags_with_connection(con, file_id, tags, source)
        con.commit()
        return total

    return submit_db_write(_write)


def get_tagger_tags(file_id: int) -> list[dict]:
    """Get all tagger tags for a file, ordered by confidence descending."""
    con = get_readonly_db()
    rows = con.execute(
        """SELECT tag_name, confidence, source, created_at
           FROM file_hailo_tags WHERE file_id = ?
           ORDER BY confidence DESC, id""",
        (file_id,),
    )
    return [dict(r) for r in rows]


def delete_tagger_tags(file_id: int, source_prefix: str = "") -> int:
    """Delete tagger tags for a file.

    Args:
        file_id: Database file ID
        source_prefix: If set, only delete tags from this source prefix
                       (e.g. "mesh:" deletes all mesh tags)

    Returns count of deleted rows.
    """
    def _write() -> int:
        con = get_db()
        if source_prefix:
            cur = con.execute(
                "DELETE FROM file_hailo_tags WHERE file_id = ? AND source LIKE ?",
                (file_id, source_prefix + "%"),
            )
        else:
            cur = con.execute(
                "DELETE FROM file_hailo_tags WHERE file_id = ?",
                (file_id,),
            )
        con.commit()
        return cur.rowcount

    return submit_db_write(_write)


def count_untagged_files() -> int:
    """Count files that have no tagger tags."""
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


def get_untagged_file_ids(limit: int = 500) -> list[int]:
    """Get IDs of files that have no tagger tags."""
    con = get_readonly_db()
    rows = con.execute(
        """SELECT f.id
           FROM files f
           WHERE f.is_deleted = 0
             AND NOT EXISTS (
               SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id
             )
           ORDER BY f.id
           LIMIT ?""",
        (limit,),
    )
    return [r[0] for r in rows]
