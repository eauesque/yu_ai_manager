"""Schema version helpers for legacy tagdb DB."""

import sqlite3
import time


def get_schema_version(con: sqlite3.Connection) -> int:
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
