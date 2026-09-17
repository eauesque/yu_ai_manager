"""Migration registry.

Register migration functions via register(),
and apply all pending migrations at once via apply_pending().
"""

import inspect
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


def _call_migration(fn: Callable[..., None], con: Any, db_key: str | None) -> None:
    """Invoke a migration, handing it ``db_key`` only if it accepts one.

    A migration that opens a *second* database -- v55 creates vectors.db --
    must encrypt it with the key the first one was opened with. Passing the
    key to every migration would mean touching 89 signatures, so the
    parameter is opt-in: a migration declares ``db_key`` when it needs it.

    Declare it by name. ``inspect.signature`` reports a ``**kwargs`` catch-all
    under its own name, so a migration written as ``fn(con, **kwargs)`` would
    silently never be handed the key -- and the failure would look like the
    one this exists to fix: a second database encrypted with the wrong key,
    reported as success.
    """
    if "db_key" in inspect.signature(fn).parameters:
        fn(con, db_key=db_key)
    else:
        fn(con)


def apply_pending(
    con: sqlite3.Connection,
    current_version: int,
    db_key: str | None = None,
) -> None:
    """Apply migrations newer than current_version in order."""
    for version, fn in get_migrations():
        if current_version < version:
            migration_con = _MigrationConnectionProxy(con)
            if con.in_transaction:
                savepoint = f"migration_v{version}"
                con.execute(f"SAVEPOINT {savepoint}")
                try:
                    _call_migration(fn, migration_con, db_key)
                except Exception:
                    con.execute(f"ROLLBACK TO {savepoint}")
                    con.execute(f"RELEASE {savepoint}")
                    raise
                con.execute(f"RELEASE {savepoint}")
            else:
                con.execute("BEGIN IMMEDIATE")
                try:
                    _call_migration(fn, migration_con, db_key)
                except Exception:
                    con.rollback()
                    raise
                con.commit()


def max_version() -> int:
    """Return the maximum registered version number."""
    return max(_registry.keys()) if _registry else 0
