"""Backup create, restore, delete, and list operations.

Separated from __init__.py to keep each module under 300 lines.
"""

import logging
import sqlite3
import time

try:
    from core.services_core.db_cipher import ENCRYPTION_ENABLED as _ENCRYPTED
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _sc
except ImportError:
    _sc = sqlite3  # type: ignore[assignment]
    _ENCRYPTED = False
    def _apply_key(con, key: str | None = None) -> None: pass  # type: ignore[misc]
from pathlib import Path
from typing import Any

from core.event_bus import emit
from core.event_bus.event_types import BACKUP_COMPLETE, BACKUP_ERROR
from core.schema_core.schema_constants import CURRENT_SCHEMA_VERSION
from core.services_core.db_api import get_config, get_db_path

from .backup_utils import (
    _META_SUFFIX,
    _PREFIX,
    _SUFFIX,
    _backup_lock,
    _enforce_retention,
    _make_filename,
    _read_meta,
    _resolve_backup_dir,
    _write_meta,
    get_last_backup_time_value,
    set_last_backup_time,
)

logger = logging.getLogger(__name__)


def create_backup(
    db_path: Path | None = None,
    backup_dir: str | None = None,
    reason: str = "manual",
    db_key: str | None = None,
) -> dict[str, Any]:
    """Create a backup of the database using sqlite3 online backup API.

    ``db_key`` defaults to the application key, which is what every in-process
    caller wants. A deployment that generates its own key must pass it: the
    online backup cannot read such a database with the application key, and
    the caller would silently fall back to a plain file copy that misses
    whatever is still in the WAL.

    Returns dict with backup filename, size, reason, etc.
    """
    if not _backup_lock.acquire(timeout=5):
        return {"error": "Another backup is already in progress"}

    try:
        if db_path is None:
            db_path = get_db_path()
        if not db_path or not db_path.exists():
            return {"error": "Database not found"}

        bdir = _resolve_backup_dir(backup_dir)

        # Pre-cleanup: retry deleting leftovers from previous failed retention
        _enforce_retention(bdir)

        filename = _make_filename()
        dest_path = bdir / filename

        # sqlite3 online backup (WAL safe); use SQLCipher to open encrypted source
        src_con = _sc.connect(str(db_path))
        _apply_key(src_con, db_key)
        dst_con = _sc.connect(str(dest_path))
        _apply_key(dst_con, db_key)
        try:
            src_con.backup(dst_con)
        finally:
            dst_con.close()
            src_con.close()

        _write_meta(dest_path, reason, source_db_path=db_path, db_key=db_key)
        _enforce_retention(bdir)

        size_bytes = dest_path.stat().st_size
        set_last_backup_time(time.time())

        emit(
            BACKUP_COMPLETE,
            {
                "filename": filename,
                "reason": reason,
                "size_bytes": size_bytes,
                "backup_dir": str(bdir),
            },
            source="backup",
        )
        logger.info("Backup created: %s (%s, %.1f MB)", filename, reason, size_bytes / 1048576)

        return {
            "success": True,
            "filename": filename,
            "size_bytes": size_bytes,
            "reason": reason,
            "backup_dir": str(bdir),
        }
    except Exception as exc:
        msg = f"Backup failed: {exc}"
        logger.error(msg, exc_info=True)
        emit(BACKUP_ERROR, {"reason": reason, "error": str(exc)}, source="backup")
        return {"error": msg}
    finally:
        _backup_lock.release()


def list_backups(backup_dir: str | None = None) -> list[dict[str, Any]]:
    """List all backups in the backup directory, newest first."""
    bdir = _resolve_backup_dir(backup_dir)
    results: list[dict[str, Any]] = []
    for p in sorted(bdir.glob(f"{_PREFIX}*{_SUFFIX}"), reverse=True):
        if p.name.endswith(_META_SUFFIX):
            continue
        meta = _read_meta(p)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        results.append({
            "filename": p.name,
            "size_bytes": size,
            "reason": meta.get("reason", "unknown"),
            "created_at": meta.get("created_at", ""),
            "schema_version": meta.get("schema_version"),
        })
    return results


def restore_backup(
    backup_filename: str,
    db_path: Path | None = None,
    backup_dir: str | None = None,
) -> dict[str, Any]:
    """Restore the database from a named backup file.

    Creates a pre_restore backup of the current DB first.
    Validates the backup file before restoring.
    """
    # Path traversal prevention
    if "/" in backup_filename or "\\" in backup_filename or ".." in backup_filename:
        return {"error": "Invalid filename"}
    if not backup_filename.startswith(_PREFIX) or not backup_filename.endswith(_SUFFIX):
        return {"error": "Invalid backup filename format"}

    bdir = _resolve_backup_dir(backup_dir)
    src_path = bdir / backup_filename
    if not src_path.exists():
        return {"error": "Backup file not found"}

    # Validate that the file is a database we can actually open.
    #
    # The plaintext ``SQLite format 3\0`` magic is only present when the build
    # is unencrypted. ``create_backup`` above applies the key to the
    # destination connection, so under SQLCipher every backup this code writes
    # is encrypted and begins with random bytes — checking for the plaintext
    # magic rejected all of them, making restore impossible on every encrypted
    # install. Keep the cheap header check where it is meaningful, and let the
    # open-and-query below be the check that actually decides.
    if not _ENCRYPTED:
        try:
            header = src_path.read_bytes()[:16]
            if not header.startswith(b"SQLite format 3\000"):
                return {"error": "Not a valid SQLite file"}
        except Exception:
            return {"error": "Failed to read backup file"}
    else:
        try:
            src_path.read_bytes()[:16]
        except Exception:
            return {"error": "Failed to read backup file"}

    # Validate 'files' table exists, and read the schema version while the
    # connection is already open.
    #
    # Note: trigger/view check is skipped for managed backups because
    # our own DB legitimately contains FTS triggers and application triggers.
    # PRAGMA trusted_schema = OFF is set to prevent untrusted code execution.
    backup_version: int | None = None
    try:
        con = _sc.connect(str(src_path))
        _apply_key(con)
        con.execute("PRAGMA trusted_schema = OFF")
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
        )
        if not cur.fetchone():
            con.close()
            return {"error": "Invalid database: 'files' table not found"}
        try:
            row = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
            backup_version = row[0] if row else None
        except Exception:
            # A backup without a readable schema_version is still restorable:
            # `files` is there, so it is a yu database. Refusing here would take
            # away the recovery instead of protecting it.
            backup_version = None
        con.close()
    except Exception as e:
        return {"error": f"Invalid SQLite file: {e}"}

    # Restoring is the one path that *creates* a database this build cannot
    # open, and the process doing it keeps running -- so the operator sees
    # success and finds out at the next start.
    #
    # Only the ahead case is refused. Restoring an older backup is a legitimate
    # recovery and the launchers migrate it on the next start; refusing it would
    # take away the recovery itself. A backup from a newer build is different:
    # no migration chain goes backwards, so nobody can repair it. Refusing is
    # also the reversible answer -- upgrade, then restore.
    if backup_version is not None and backup_version > CURRENT_SCHEMA_VERSION:
        return {
            "error": (
                f"This backup is at schema v{backup_version}, which is newer than this "
                f"build (v{CURRENT_SCHEMA_VERSION}). Restoring it would leave a database "
                "this build cannot open, and no migration goes backwards. Use a newer "
                "build, then restore. Nothing has been modified."
            )
        }

    if db_path is None:
        db_path = get_db_path()

    # Create pre-restore backup
    pre_result = create_backup(db_path, backup_dir, reason="pre_restore")
    if "error" in pre_result:
        logger.warning("Pre-restore backup failed: %s", pre_result["error"])
        # Continue anyway - the user explicitly wants to restore

    # Overwrite current DB using sqlite3 backup API; use SQLCipher for encrypted DBs
    try:
        src_con = _sc.connect(str(src_path))
        _apply_key(src_con)
        dst_con = _sc.connect(str(db_path))
        _apply_key(dst_con)
        try:
            src_con.backup(dst_con)
        finally:
            dst_con.close()
            src_con.close()
    except Exception as exc:
        return {"error": f"Restore failed: {exc}"}

    logger.info("Database restored from %s", backup_filename)
    payload: dict[str, Any] = {
        "success": True,
        "message": "Database restored successfully",
        "restored_from": backup_filename,
        "pre_restore_backup": pre_result.get("filename", ""),
    }
    # Say it in the response, not only the log: the caller is a UI that reports
    # "restored successfully", and the database it just wrote needs a migration
    # before anything can open it. Silence here is what let this path hand back
    # a broken library as a success.
    if backup_version is not None and backup_version < CURRENT_SCHEMA_VERSION:
        notice = (
            f"The restored database is at schema v{backup_version}; this build needs "
            f"v{CURRENT_SCHEMA_VERSION}. Starting through the launcher migrates it "
            "automatically. A headless deployment (systemd, a bare yu-server) must run "
            "the Python version once before it will start."
        )
        logger.warning("%s", notice)
        payload["schema_version"] = backup_version
        payload["needs_migration"] = True
        payload["migration_notice"] = notice
    return payload


def delete_backup(
    backup_filename: str,
    backup_dir: str | None = None,
) -> dict[str, Any]:
    """Delete a specific backup file and its meta sidecar."""
    # Path traversal prevention
    if "/" in backup_filename or "\\" in backup_filename or ".." in backup_filename:
        return {"error": "Invalid filename"}
    if not backup_filename.startswith(_PREFIX) or not backup_filename.endswith(_SUFFIX):
        return {"error": "Invalid backup filename format"}

    bdir = _resolve_backup_dir(backup_dir)
    target = bdir / backup_filename
    if not target.exists():
        return {"error": "Backup file not found"}

    try:
        target.unlink()
        meta = target.with_suffix(_SUFFIX + _META_SUFFIX)
        if meta.exists():
            meta.unlink()
    except Exception as exc:
        return {"error": f"Failed to delete backup: {exc}"}

    logger.info("Deleted backup: %s", backup_filename)
    return {"success": True, "deleted": backup_filename}


def get_last_backup_time() -> float | None:
    """Return the epoch timestamp of the last successful backup, or None."""
    return get_last_backup_time_value()


def is_within_cooldown() -> bool:
    """Check if a backup was created recently (within cooldown period)."""
    t = get_last_backup_time_value()
    if t is None:
        return False
    cfg = get_config()
    cooldown_min = cfg.get("backup", {}).get("cooldown_minutes", 5)
    return (time.time() - t) < cooldown_min * 60
