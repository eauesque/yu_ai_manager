"""Schema migration version helpers."""

import time

try:
    from core.services_core.db_cipher import sqlite3
except ImportError:
    import sqlite3  # type: ignore[no-redef]


def get_schema_version(con) -> int:
    try:
        row = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def set_schema_version(con: sqlite3.Connection, version: int, description: str) -> None:
    con.execute(
        "INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
        (version, int(time.time()), description),
    )
