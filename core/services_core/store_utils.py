"""Common utilities for the Store pattern.

DB access helpers used by all *_core/store.py modules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

T = TypeVar("T")
TItem = TypeVar("TItem")
_IN_CHUNK_SIZE = 500


def _chunks(items: list[TItem], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def fetch_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    """Return a single row as dict. Returns None if not found."""
    con = get_db()
    row = con.execute(sql, params).fetchone()
    return dict(row) if row else None


def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Return all rows as a list of dicts."""
    con = get_db()
    rows = con.execute(sql, params)
    return [dict(r) for r in rows]


def fetch_scalar(sql: str, params: tuple = (), default: Any = None) -> Any:
    """Return a single scalar value. Returns default if not found."""
    con = get_db()
    row = con.execute(sql, params).fetchone()
    return row[0] if row else default


def execute_write(sql: str, params: tuple = ()) -> int:
    """Execute a write SQL statement and return the affected row count. Auto-commits."""
    def _write() -> int:
        con = get_db()
        cur = con.execute(sql, params)
        con.commit()
        return cur.rowcount

    return submit_db_write(_write)


def execute_in_tx(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Execute fn(con, *args, **kwargs) within a transaction.

    Rolls back on exception. Commits on success.
    """
    def _write() -> Any:
        con = get_db()
        try:
            result = fn(con, *args, **kwargs)
            con.commit()
            return result
        except Exception:
            con.rollback()
            raise

    return submit_db_write(_write)


def validate_file_ids(file_ids: list[int]) -> set[int]:
    """Return the set of file_ids that exist in the files table (is_deleted=0)."""
    if not file_ids:
        return set()
    con = get_readonly_db()
    valid_ids: set[int] = set()
    for chunk in _chunks(file_ids):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT id FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
            chunk,
        )
        valid_ids.update(int(row[0]) for row in cursor)
    return valid_ids
