"""Persistent scan error recording and retrieval.

Tracks files/archives that failed during scanning (encoding errors,
timeouts, corrupt archives) so they can be reviewed and retried.
"""

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

_SCAN_ERROR_COLUMNS = (
    "id, path, error_type, error_detail, encodings_tried, created_at, resolved"
)


def record_scan_error(
    con: sqlite3.Connection,
    path: str,
    error_type: str,
    error_detail: str = "",
    encodings_tried: list[str] | None = None,
) -> int:
    """Insert or update a scan error record.

    If an unresolved error for the same *path* and *error_type* already
    exists, the detail is updated instead of creating a duplicate.
    Returns the row id.
    """
    enc_json = json.dumps(encodings_tried or [], ensure_ascii=False)

    # Upsert: update existing unresolved error for same path+type
    existing = con.execute(
        "SELECT id FROM scan_errors WHERE path=? AND error_type=? AND resolved=0",
        (path, error_type),
    ).fetchone()

    if existing:
        row_id = existing[0] if isinstance(existing, (tuple, list)) else existing["id"]
        con.execute(
            "UPDATE scan_errors SET error_detail=?, encodings_tried=?, "
            "created_at=datetime('now') WHERE id=?",
            (error_detail, enc_json, row_id),
        )
        logger.debug("Updated scan error #%d: %s", row_id, path)
        return row_id

    cur = con.execute(
        "INSERT INTO scan_errors (path, error_type, error_detail, encodings_tried) "
        "VALUES (?, ?, ?, ?)",
        (path, error_type, error_detail, enc_json),
    )
    logger.debug("Recorded scan error #%d: %s (%s)", cur.lastrowid, path, error_type)
    return cur.lastrowid  # type: ignore[return-value]


def get_scan_errors(
    con: sqlite3.Connection,
    error_type: str | None = None,
    resolved: bool | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Retrieve scan errors with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []
    if error_type is not None:
        clauses.append("error_type = ?")
        params.append(error_type)
    if resolved is not None:
        clauses.append("resolved = ?")
        params.append(1 if resolved else 0)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT {_SCAN_ERROR_COLUMNS} FROM scan_errors{where} ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)

    rows = con.execute(sql, params)
    result = []
    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {
            "id": row[0], "path": row[1], "error_type": row[2],
            "error_detail": row[3], "encodings_tried": row[4],
            "created_at": row[5], "resolved": row[6],
        }
        # Parse encodings_tried back to list
        enc = d.get("encodings_tried", "[]")
        if isinstance(enc, str):
            try:
                d["encodings_tried"] = json.loads(enc)
            except (json.JSONDecodeError, TypeError):
                d["encodings_tried"] = []
        result.append(d)
    return result


def resolve_scan_error(con: sqlite3.Connection, error_id: int) -> bool:
    """Mark a scan error as resolved. Returns True if found."""
    cur = con.execute(
        "UPDATE scan_errors SET resolved=1 WHERE id=? AND resolved=0",
        (error_id,),
    )
    return cur.rowcount > 0


def resolve_scan_errors_by_path(con: sqlite3.Connection, path: str) -> int:
    """Mark all unresolved errors for *path* as resolved."""
    cur = con.execute(
        "UPDATE scan_errors SET resolved=1 WHERE path=? AND resolved=0",
        (path,),
    )
    return cur.rowcount


def clear_resolved_errors(con: sqlite3.Connection) -> int:
    """Delete all resolved errors. Returns count deleted."""
    cur = con.execute("DELETE FROM scan_errors WHERE resolved=1")
    return cur.rowcount


def get_unresolved_count(con: sqlite3.Connection) -> int:
    """Count unresolved scan errors."""
    row = con.execute("SELECT COUNT(*) FROM scan_errors WHERE resolved=0").fetchone()
    return row[0] if row else 0
