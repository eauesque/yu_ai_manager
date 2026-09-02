"""Sandbox Proxy: Restrict resource access via ServiceRegistry based on permissions.

SandboxedDB: Extensions with only db:read deny non-SELECT SQL
SandboxedFS: Restrict file access according to permission scope
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SandboxPermissionError(Exception):
    """Sandbox permission violation exception.

    Raised when an extension attempts an operation beyond its access permissions.
    Can be caught and handled appropriately within the extension.
    """


# ---------------------------------------------------------------------------
# SandboxedDB: restrict SQL operations based on permissions
# ---------------------------------------------------------------------------

# SQL prefixes allowed for read-only access
_READ_ONLY_PREFIXES = (
    "SELECT",
    "EXPLAIN",
    "WITH",  # CTE (preamble for SELECT)
)
_READ_ONLY_PRAGMAS = (
    "PRAGMA TABLE_INFO",
    "PRAGMA TABLE_XINFO",
    "PRAGMA INDEX_INFO",
    "PRAGMA INDEX_LIST",
    "PRAGMA FOREIGN_KEY_LIST",
    "PRAGMA DATABASE_LIST",
)
_READ_ONLY_PRAGMA_NAMES = {
    "database_list",
    "foreign_key_list",
    "index_info",
    "index_list",
    "query_only",
    "table_info",
    "table_xinfo",
}
_SQLITE_WRITE_ACTIONS = {
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ANALYZE,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_INDEX,
    sqlite3.SQLITE_CREATE_TEMP_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
    sqlite3.SQLITE_CREATE_TEMP_VIEW,
    sqlite3.SQLITE_CREATE_TRIGGER,
    sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_CREATE_VTABLE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_DROP_INDEX,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_INDEX,
    sqlite3.SQLITE_DROP_TEMP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER,
    sqlite3.SQLITE_DROP_TEMP_VIEW,
    sqlite3.SQLITE_DROP_TRIGGER,
    sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_DROP_VTABLE,
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_REINDEX,
    sqlite3.SQLITE_SAVEPOINT,
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_UPDATE,
}


def _readonly_authorizer(action, arg1, arg2, _database, _trigger) -> int:
    if action in _SQLITE_WRITE_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        name = (arg1 or "").lower()
        if name not in _READ_ONLY_PRAGMA_NAMES or (name == "query_only" and arg2 is not None):
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class SandboxedConnection:
    """Connection wrapper that restricts SQL operations based on permissions."""

    def __init__(self, real_conn: Any, caller_name: str, can_write: bool):
        self._real = real_conn
        self._caller = caller_name
        self._can_write = can_write
        if not can_write:
            self._real.execute("PRAGMA query_only=ON")
            self._real.set_authorizer(_readonly_authorizer)

    def execute(self, sql: str, params: Any = None) -> Any:
        if not self._can_write:
            self._check_read_only(sql)
        cursor = self._real.execute(sql, params) if params is not None else self._real.execute(sql)
        return SandboxedCursor(cursor, self)

    def executemany(self, sql: str, params_seq: Any) -> Any:
        if not self._can_write:
            self._check_read_only(sql)
        return SandboxedCursor(self._real.executemany(sql, params_seq), self)

    def executescript(self, sql_script: str) -> Any:
        if not self._can_write:
            raise SandboxPermissionError(
                f"Extension '{self._caller}' は db:write 権限がないため "
                f"executescript() を実行できません"
            )
        return self._real.executescript(sql_script)

    def _check_read_only(self, sql: str) -> None:
        """Verify SQL statement prefix and deny non-read operations."""
        normalized = sql.strip()
        # Skip comments
        while normalized.startswith("--"):
            newline = normalized.find("\n")
            if newline == -1:
                break
            normalized = normalized[newline + 1:].strip()

        upper = normalized.upper()
        if upper.startswith("PRAGMA"):
            if upper.rstrip("; ") == "PRAGMA QUERY_ONLY" or upper.startswith(_READ_ONLY_PRAGMAS):
                return
            raise SandboxPermissionError(
                f"Extension '{self._caller}' は db:write 権限がないため "
                f"この PRAGMA を実行できません: {normalized[:50]}..."
            )
        if not upper.startswith(_READ_ONLY_PREFIXES):
            raise SandboxPermissionError(
                f"Extension '{self._caller}' は db:write 権限がないため "
                f"この SQL を実行できません: {normalized[:50]}..."
            )

    # --- Methods delegated transparently ---

    def commit(self) -> None:
        if not self._can_write:
            raise SandboxPermissionError(
                f"Extension '{self._caller}' は db:write 権限がないため "
                f"commit() を実行できません"
            )
        return self._real.commit()

    def rollback(self) -> None:
        return self._real.rollback()

    def close(self) -> None:
        return self._real.close()

    def cursor(self) -> Any:
        return SandboxedCursor(self._real.cursor(), self)

    @property
    def row_factory(self) -> Any:
        return self._real.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._real.row_factory = value

    @property
    def isolation_level(self) -> str | None:
        return self._real.isolation_level

    @isolation_level.setter
    def isolation_level(self, value: str | None) -> None:
        self._real.isolation_level = value

    def __enter__(self) -> SandboxedConnection:
        self._real.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._real.__exit__(*args)


class SandboxedCursor:
    """Cursor wrapper preserving the connection's SQL permission checks."""

    def __init__(self, real_cursor: Any, connection: SandboxedConnection):
        self._real = real_cursor
        self._connection = connection

    def execute(self, sql: str, params: Any = None) -> Any:
        if not self._connection._can_write:
            self._connection._check_read_only(sql)
        self._real.execute(sql) if params is None else self._real.execute(sql, params)
        return self

    def executemany(self, sql: str, params_seq: Any) -> Any:
        if not self._connection._can_write:
            self._connection._check_read_only(sql)
        self._real.executemany(sql, params_seq)
        return self

    def executescript(self, sql_script: str) -> Any:
        if not self._connection._can_write:
            raise SandboxPermissionError(
                f"Extension '{self._connection._caller}' は db:write 権限がないため "
                "executescript() を実行できません"
            )
        return self._real.executescript(sql_script)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    @property
    def connection(self) -> SandboxedConnection:
        return self._connection


def _open_extension_readonly_db(*, include_custom_functions: bool = True) -> Any:
    """Open the application DB with SQLite's mode=ro write boundary."""
    from core.services_core.db_api import get_db_path
    from core.services_core.db_cipher import apply_key, sqlite3
    from core.services_core.db_state_functions import register_custom_functions
    from core.services_core.db_state_runtime import ensure_db_migrated

    ensure_db_migrated()
    conn = sqlite3.connect(
        f"{get_db_path().resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    try:
        apply_key(conn)
        conn.row_factory = sqlite3.Row
        if include_custom_functions:
            register_custom_functions(conn)
        conn.execute("PRAGMA query_only=ON")
        conn.set_authorizer(_readonly_authorizer)
        return conn
    except Exception:
        conn.close()
        raise


class SandboxedDB:
    """DB proxy for extensions with db:read only.

    Returned in place of ServiceRegistry.get("db").
    Returns a SandboxedConnection when called.
    """

    def __init__(self, real_db_fn: Any, caller_name: str, can_write: bool):
        self._db_fn = real_db_fn
        self._caller = caller_name
        self._can_write = can_write

    def __call__(self) -> SandboxedConnection:
        """Wrapper for real_db_fn(). Returns a SandboxedConnection."""
        real_conn = self._db_fn() if self._can_write else _open_extension_readonly_db()
        return SandboxedConnection(real_conn, self._caller, self._can_write)


# ---------------------------------------------------------------------------
# SandboxedFS: restrict file access based on permissions
# ---------------------------------------------------------------------------


class SandboxedFS:
    """Proxy that restricts file access based on permissions.

    Restricts accessible paths according to fs permission scope:
    - fs:read:own / fs:write:own  -> extension's own directory only
    - fs:read:scan_roots         -> configured scan roots
    - fs:read:any / fs:write:any -> unrestricted
    """

    def __init__(
        self,
        caller_name: str,
        allowed_read_paths: list[str],
        allowed_write_paths: list[str],
        can_read_any: bool = False,
        can_write_any: bool = False,
    ):
        self._caller = caller_name
        self._read_paths = [os.path.realpath(p) for p in allowed_read_paths]
        self._write_paths = [os.path.realpath(p) for p in allowed_write_paths]
        self._can_read_any = can_read_any
        self._can_write_any = can_write_any

    def _check_read(self, path: str) -> None:
        """Check read access permission."""
        if self._can_read_any:
            return
        real = os.path.realpath(path)
        for allowed in self._read_paths:
            if real.startswith(allowed + os.sep) or real == allowed:
                return
        raise SandboxPermissionError(
            f"Extension '{self._caller}' はこのパスを読み取れません: {path}"
        )

    def _check_write(self, path: str) -> None:
        """Check write access permission."""
        if self._can_write_any:
            return
        real = os.path.realpath(path)
        for allowed in self._write_paths:
            if real.startswith(allowed + os.sep) or real == allowed:
                return
        raise SandboxPermissionError(
            f"Extension '{self._caller}' はこのパスに書き込めません: {path}"
        )

    def read(self, path: str) -> bytes:
        """Read a file."""
        self._check_read(path)
        return Path(path).read_bytes()

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read a text file."""
        self._check_read(path)
        return Path(path).read_text(encoding=encoding)

    def write(self, path: str, data: bytes) -> None:
        """Write to a file."""
        self._check_write(path)
        Path(path).write_bytes(data)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """Write to a text file."""
        self._check_write(path)
        Path(path).write_text(content, encoding=encoding)

    def exists(self, path: str) -> bool:
        """Check file existence (requires read permission)."""
        self._check_read(path)
        return Path(path).exists()

    def listdir(self, path: str) -> list:
        """List directory contents (requires read permission)."""
        self._check_read(path)
        return os.listdir(path)
