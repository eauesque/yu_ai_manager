"""Utility functions for database backup operations.

Shared helpers used by backup_ops.py and re-exported from __init__.py.
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.services_core.db_api import get_config, get_db_path

logger = logging.getLogger(__name__)

_backup_lock = threading.Lock()

_PREFIX = "yu_ai_manager_"
_SUFFIX = ".db"
_META_SUFFIX = ".meta.json"

# Timestamp of the last successful backup (epoch float)
_last_backup_time: float | None = None


def get_last_backup_time_value() -> float | None:
    """Return current _last_backup_time value."""
    return _last_backup_time


def set_last_backup_time(value: float) -> None:
    """Set the _last_backup_time global."""
    global _last_backup_time
    _last_backup_time = value


def _resolve_backup_dir(backup_dir: str | None = None) -> Path:
    """Resolve the backup directory path.

    If backup_dir is empty/None, uses ``<db_parent>/backup/``.
    """
    if backup_dir:
        p = Path(backup_dir)
    else:
        cfg = get_config()
        configured = cfg.get("backup", {}).get("backup_dir", "")
        if configured:
            p = Path(configured)
        else:
            db_path = get_db_path()
            p = db_path.parent / "backup"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_filename() -> str:
    """Generate a backup filename with current timestamp."""
    ts = datetime.now(tz=UTC).astimezone().strftime("%Y%m%d_%H%M%S")
    return f"{_PREFIX}{ts}{_SUFFIX}"


def _write_meta(
    backup_path: Path,
    reason: str,
    source_db_path: Path | None = None,
) -> None:
    """Write a sidecar .meta.json file next to the backup."""
    meta = {
        "reason": reason,
        # Naive on purpose: `backup_ops` hands this string straight to the
        # user; an aware `.isoformat()` would append the offset to it.
        "created_at": datetime.now().isoformat(),  # noqa: DTZ005
        "created_epoch": time.time(),
    }
    # Read schema version from the backup itself
    try:
        con = sqlite3.connect(str(backup_path))
        row = con.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if row:
            meta["schema_version"] = row[0]
        con.close()
    except Exception:
        logger.warning("backup schema version was unreadable", exc_info=True)
    if source_db_path:
        try:
            st = source_db_path.stat()
            meta["source_db_path"] = str(source_db_path.resolve())
            meta["source_db_size"] = st.st_size
            meta["source_db_mtime_ns"] = st.st_mtime_ns
        except Exception:
            logger.debug("source DB stat unavailable", exc_info=True)
    meta_path = backup_path.with_suffix(_SUFFIX + _META_SUFFIX)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_meta(backup_path: Path) -> dict[str, Any]:
    """Read the sidecar .meta.json if it exists."""
    meta_path = backup_path.with_suffix(_SUFFIX + _META_SUFFIX)
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("backup metadata was unreadable", exc_info=True)
    return {}


def _safe_unlink(path: Path, retries: int = 3, delay: float = 0.5) -> bool:
    """Delete a file with retry for Windows file-lock issues."""
    for attempt in range(retries):
        try:
            path.unlink()
            return True
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                return False
        except FileNotFoundError:
            return True
        except Exception:
            return False
    return False


def _enforce_retention(backup_dir: Path) -> int:
    """Delete oldest backups exceeding max_generations. Returns count deleted."""
    cfg = get_config()
    max_gen = cfg.get("backup", {}).get("max_generations", 5)
    if max_gen <= 0:
        return 0

    backups = sorted(backup_dir.glob(f"{_PREFIX}*{_SUFFIX}"), key=lambda p: p.name)
    # Exclude .meta.json files from the list
    backups = [b for b in backups if not b.name.endswith(_META_SUFFIX)]
    removed = 0
    failed = 0
    while len(backups) > max_gen:
        oldest = backups.pop(0)
        if _safe_unlink(oldest):
            # Also remove meta sidecar
            meta = oldest.with_suffix(_SUFFIX + _META_SUFFIX)
            if meta.exists():
                _safe_unlink(meta)
            removed += 1
            logger.info("Retention: deleted old backup %s", oldest.name)
        else:
            failed += 1
            logger.warning("Failed to delete old backup %s (file locked?)", oldest.name)
    if failed:
        logger.warning("Retention: %d file(s) could not be deleted", failed)
    return removed
