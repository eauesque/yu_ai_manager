"""Shared scanner helpers."""

import sqlite3
from typing import Any

from core.models_core.models_files import get_file_row
from core.schema_core.schema import CURRENT_PARSER_VERSION


def extract_metadata_enhanced(_p) -> dict[str, Any]:
    """Legacy compatibility stub."""
    return {"success": False}


def needs_backfill(con: sqlite3.Connection) -> int:
    """Return count of non-deleted files with NULL hash.

    Call once at scan start.  Returns 0 when all hashes are populated,
    allowing the caller to skip per-file backfill checks entirely.
    """
    row = con.execute(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NULL"
    ).fetchone()
    return row[0]


def should_rescan(con: sqlite3.Connection, path: str, mtime: int, size: int, force: bool) -> bool:
    """Return True when file should be re-scanned."""
    if force:
        return True
    row = get_file_row(con, path)
    if row is None:
        return True
    _fid, old_mtime, old_size, is_deleted, _hash, old_parser_version = row
    if is_deleted:
        return True
    if old_mtime != mtime or old_size != size:
        return True
    return old_parser_version < CURRENT_PARSER_VERSION
