"""Post-migration SQLite validation helpers."""

import sqlite3
from typing import Any


def run_foreign_key_check(con: sqlite3.Connection) -> list[tuple[Any, ...]]:
    """Return foreign key violations reported by SQLite."""
    return [tuple(row) for row in con.execute("PRAGMA foreign_key_check").fetchall()]


def run_integrity_check(con: sqlite3.Connection) -> str:
    """Run SQLite integrity_check and return the first result string."""
    row = con.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row and row[0] is not None else ""
