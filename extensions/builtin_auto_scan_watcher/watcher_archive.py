"""Archive scanning logic for the auto-scan watcher.

Handles ZIP and 7z archive event processing.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def flush_archives(
    con: sqlite3.Connection, batch: dict[str, tuple], config: dict,
) -> tuple:
    """Scan or delete archive entries. Returns (added, modified, deleted, errors)."""
    from core.scan.runtime_prepare import SCAN_EXTS

    added = modified = deleted = errors = 0
    exts_tuple = tuple(SCAN_EXTS)

    for path, (action, _ts) in batch.items():
        try:
            ext = Path(path).suffix.lower()
            if action == "deleted":
                deleted += mark_archive_entries_deleted(con, path)
            else:
                p = Path(path)
                if not p.exists():
                    logger.warning("Watcher: archive not found (may still be writing): %s", path)
                    continue
                logger.info("Watcher: scanning archive %s (action=%s)", path, action)
                if ext == ".zip":
                    a, m, e = _scan_zip_entries(con, str(p), exts_tuple, config)
                elif ext == ".7z":
                    a, m, e = _scan_7z_entries(con, str(p), exts_tuple, config)
                else:
                    continue
                added += a
                modified += m
                errors += e
                logger.info("Watcher: archive %s done: +%d ~%d err=%d", path, a, m, e)
        except Exception:
            logger.warning("Watcher: error processing archive %s", path, exc_info=True)
            errors += 1

    return added, modified, deleted, errors


def _scan_zip_entries(
    con: sqlite3.Connection, zip_path: str, exts: tuple, config: dict,
) -> tuple:
    """Scan entries inside a ZIP. Returns (added, modified, errors)."""
    from core.scan.zip_worker_single import scan_one_zip
    from core.zip_core.zip_listing import list_images_in_zip

    added = modified = errors = 0
    try:
        entries = list_images_in_zip(zip_path, exts)
    except Exception:
        logger.warning("Watcher: failed to list ZIP %s", zip_path, exc_info=True)
        return 0, 0, 1

    logger.info("Watcher: ZIP %s contains %d image entries", zip_path, len(entries))
    for entry in entries:
        full_path = f"{zip_path}!{entry}"
        try:
            result = scan_one_zip(con, full_path, config, force=False)
            if result:
                if result[0] == "added":
                    added += 1
                else:
                    modified += 1
        except Exception:
            logger.warning("Watcher: error scanning ZIP entry %s", full_path, exc_info=True)
            errors += 1
    return added, modified, errors


def _scan_7z_entries(
    con: sqlite3.Connection, archive_path: str, exts: tuple, config: dict,
) -> tuple:
    """Scan entries inside a 7z. Returns (added, modified, errors)."""
    from core.scan.sevenz_worker_single import scan_one_7z
    from core.sevenz_core.sevenz_support import list_images_in_7z

    added = modified = errors = 0
    try:
        entries = list_images_in_7z(archive_path, exts)
    except Exception:
        logger.warning("Watcher: failed to list 7z %s", archive_path, exc_info=True)
        return 0, 0, 1

    logger.info("Watcher: 7z %s contains %d image entries", archive_path, len(entries))
    for entry in entries:
        full_path = f"{archive_path}!{entry}"
        try:
            result = scan_one_7z(con, full_path, config, force=False)
            if result:
                if result[0] == "added":
                    added += 1
                else:
                    modified += 1
        except Exception:
            logger.warning("Watcher: error scanning 7z entry %s", full_path, exc_info=True)
            errors += 1
    return added, modified, errors


def mark_archive_entries_deleted(con: sqlite3.Connection, archive_path: str) -> int:
    """Mark all DB entries belonging to an archive as deleted."""
    from core.platform import normalize_path
    norm = normalize_path(Path(archive_path))
    prefix = norm + "!"
    cur = con.execute(
        "UPDATE files SET is_deleted=1 WHERE path LIKE ? AND is_deleted=0",
        (prefix + "%",),
    )
    count = cur.rowcount
    if count:
        logger.info("Watcher: marked %d entries deleted for archive %s", count, archive_path)
    return count
