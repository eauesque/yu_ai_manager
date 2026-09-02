"""Extension DB migration helper.

Provides version management utilities for extensions to idempotently
create and update their own tables via the on_db_migrate hook.

Usage (extension side)::

    from core.extensions_core.extensions_db_migrate import (
        get_extension_schema_version,
        set_extension_schema_version,
    )

    def on_db_migrate(con):
        cur = get_extension_schema_version(con, "builtin-my-ext")
        if cur < 1:
            con.execute("CREATE TABLE IF NOT EXISTS ...")
            set_extension_schema_version(con, "builtin-my-ext", 1, "initial tables")
        con.commit()
"""

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)


def get_extension_schema_version(con: sqlite3.Connection, extension_name: str) -> int:
    """Return the current schema version for the extension. Returns 0 if unregistered."""
    try:
        row = con.execute(
            "SELECT MAX(version) FROM extension_schema_versions WHERE extension_name = ?",
            (extension_name,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def set_extension_schema_version(
    con: sqlite3.Connection,
    extension_name: str,
    version: int,
    description: str = "",
) -> None:
    """Record the extension's schema version."""
    con.execute(
        """INSERT INTO extension_schema_versions
           (extension_name, version, applied_at, description)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(extension_name, version) DO UPDATE SET
             applied_at=excluded.applied_at,
             description=excluded.description""",
        (extension_name, version, int(time.time()), description),
    )


def run_extension_db_migrations(registry, modules: dict, con: sqlite3.Connection) -> None:
    """Execute the on_db_migrate hook for all extensions.

    Extensions idempotently create tables using CREATE TABLE IF NOT EXISTS
    and manage their own version via extension_schema_versions.
    """
    entries = registry.get_registered("on_db_migrate").get("on_db_migrate", [])
    if not entries:
        return

    for entry in entries:
        ext_name = entry.get("extension")
        if not ext_name:
            continue
        module = modules.get(ext_name)
        if module is None:
            continue
        migrate_fn = getattr(module, "on_db_migrate", None)
        if migrate_fn is None:
            continue
        try:
            migrate_fn(con)
            logger.debug("Extension DB migrate: %s OK", ext_name)
        except Exception as exc:
            logger.error("Extension DB migrate failed for %s: %s", ext_name, exc)
