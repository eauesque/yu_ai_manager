"""Persistent key-value state for runtime markers (e.g. backfill progress).

Backed by the `kv_state` SQLite table (added in schema v71). All writes
must go through the single-writer thread per
SQLITE_IMPLEMENTATION_GUIDE.md § 3.2; the helpers here wrap that
internally, so callers just invoke ``kv_state.set(key, value)``.
"""

from __future__ import annotations

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write


def get(key: str, default: str | None = None) -> str | None:
    """Read a kv_state entry. Returns ``default`` (None by default) if missing."""
    row = get_readonly_db().execute(
        "SELECT value FROM kv_state WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else default


def set(key: str, value: str) -> None:
    """Set a kv_state entry through the writer thread (UPSERT)."""
    submit_db_write(lambda: _set_inner_write(key, value))


def delete(key: str) -> None:
    """Delete a kv_state entry through the writer thread."""
    submit_db_write(lambda: _delete_inner_write(key))


def _set_inner_write(key: str, value: str) -> None:
    con = get_db()
    con.execute(
        "INSERT INTO kv_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET "
        "value = excluded.value, "
        "updated_at = strftime('%s','now')",
        (key, value),
    )
    con.commit()


def _delete_inner_write(key: str) -> None:
    con = get_db()
    con.execute("DELETE FROM kv_state WHERE key = ?", (key,))
    con.commit()
