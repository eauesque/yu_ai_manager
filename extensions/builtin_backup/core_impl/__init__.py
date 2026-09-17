"""Database backup core logic.

Provides create/list/restore/delete operations for server-side DB backups.
Uses sqlite3.Connection.backup() for WAL-safe online copies.

NOTE: Operations have been split into backup_utils.py (helpers) and
backup_ops.py (CRUD operations). This module re-exports all public
symbols for backward compatibility.
"""

from .backup_ops import (  # noqa: F401 -- re-export
    create_backup,
    delete_backup,
    get_last_backup_time,
    is_within_cooldown,
    list_backups,
    restore_backup,
)
