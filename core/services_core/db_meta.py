"""Cached aggregate stats in db_meta table.

Avoids expensive COUNT(*) at startup by persisting stats that are
updated at scan completion and other write events.
"""

import json
import logging
import sqlite3
import time

from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)


def get_meta(con: sqlite3.Connection, key: str) -> str | None:
    """Read a value from db_meta. Returns None if not found."""
    try:
        row = con.execute(
            "SELECT value FROM db_meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        # Handle both Row and tuple
        return row["value"] if isinstance(row, sqlite3.Row) else row[0]
    except Exception:
        return None


def get_meta_int(con: sqlite3.Connection, key: str, default: int = 0) -> int:
    """Read an integer value from db_meta."""
    val = get_meta(con, key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_meta_json(con: sqlite3.Connection, key: str) -> dict | None:
    """Read a JSON object from db_meta."""
    val = get_meta(con, key)
    if not val:
        return None
    try:
        data = json.loads(val)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    """Write a value to db_meta (upsert)."""
    now = int(time.time())
    con.execute(
        """
        INSERT INTO db_meta (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, value, now),
    )


def refresh_file_stats(con: sqlite3.Connection, parser_version: int) -> dict:
    """Recompute and cache file aggregate stats.

    Called after scan completion or metadata changes.
    Returns the computed stats dict.
    """
    # Single pass over files: GROUP BY meta_source, with conditional sum
    # for old-parser count. Folds 3 separate full scans into 1.
    tag_count = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    schema_version = con.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()[0]

    total = 0
    old_parser = 0
    meta_stats: dict[str, int] = {}
    for row in con.execute(
        "SELECT COALESCE(meta_source,'unknown') AS ms, "
        "COUNT(*) AS c, "
        "SUM(CASE WHEN parser_version < ? THEN 1 ELSE 0 END) AS old_c "
        "FROM files WHERE is_deleted=0 "
        "GROUP BY ms ORDER BY c DESC",
        (parser_version,),
    ).fetchall():
        meta_stats[row[0]] = row[1]
        total += row[1]
        old_parser += row[2] or 0

    set_meta(con, "total_files", str(total))
    set_meta(con, "tag_count", str(tag_count))
    set_meta(con, "schema_version", str(schema_version or 0))
    set_meta(con, "meta_stats", json.dumps(meta_stats, ensure_ascii=False, separators=(",", ":")))
    set_meta(con, "old_parser_count", str(old_parser))
    con.commit()

    stats = {
        "total_files": total,
        "tag_count": tag_count,
        "schema_version": schema_version,
        "meta_stats": meta_stats,
        "old_parser_count": old_parser,
    }
    logger.debug("[db_meta] Stats refreshed: %s", stats)
    return stats


def refresh_file_stats_serialized(parser_version: int) -> dict:
    """Recompute cached file stats on the single SQLite writer thread."""

    def _write() -> dict:
        from core.services_core.db_api import get_db

        con = get_db()
        return refresh_file_stats(con, parser_version)

    return submit_db_write(_write)
