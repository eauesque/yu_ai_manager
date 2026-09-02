"""Migration registry.

Register migration functions via register(),
and apply all pending migrations at once via apply_pending().
"""

import sqlite3
from collections.abc import Callable
from typing import Any

# Holds (version, fn) pairs
_registry: dict[int, Callable[[sqlite3.Connection], None]] = {}


class _MigrationConnectionProxy:
    """Connection proxy that keeps executescript inside caller transactions."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def __getattr__(self, name: str) -> Any:
        return getattr(self._con, name)

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        statement = ""
        last_cursor: sqlite3.Cursor | None = None
        for char in sql_script:
            statement += char
            if sqlite3.complete_statement(statement):
                sql = statement.strip()
                statement = ""
                if sql:
                    last_cursor = self._con.execute(sql)

        if statement.strip():
            raise sqlite3.OperationalError("incomplete SQL statement")

        return last_cursor if last_cursor is not None else self._con.cursor()


def register(version: int, fn: Callable[[sqlite3.Connection], None]) -> None:
    """Register a migration function by version number."""
    if version in _registry:
        raise ValueError(f"Migration v{version} is already registered")
    _registry[version] = fn


def get_migrations() -> list[tuple[int, Callable[[sqlite3.Connection], None]]]:
    """Return registered migrations sorted by version in ascending order."""
    return sorted(_registry.items())


def apply_pending(con: sqlite3.Connection, current_version: int) -> None:
    """Apply migrations newer than current_version in order."""
    for version, fn in get_migrations():
        if current_version < version:
            migration_con = _MigrationConnectionProxy(con)
            if con.in_transaction:
                savepoint = f"migration_v{version}"
                con.execute(f"SAVEPOINT {savepoint}")
                try:
                    fn(migration_con)
                except Exception:
                    con.execute(f"ROLLBACK TO {savepoint}")
                    con.execute(f"RELEASE {savepoint}")
                    raise
                con.execute(f"RELEASE {savepoint}")
            else:
                con.execute("BEGIN IMMEDIATE")
                try:
                    fn(migration_con)
                except Exception:
                    con.rollback()
                    raise
                con.commit()


def max_version() -> int:
    """Return the maximum registered version number."""
    return max(_registry.keys()) if _registry else 0
