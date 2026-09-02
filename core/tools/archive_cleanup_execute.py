"""Archive cleanup execution -- delete archives or folders.

Processes user-selected cleanup actions: delete archive files,
delete extracted folders, or skip.  Includes robust error handling
for permission issues and locked files.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_ERRORS = 500


def _force_unlink(p: Path) -> None:
    """Delete a file, retrying with read-only flag removal on PermissionError."""
    try:
        p.unlink()
    except PermissionError:
        try:
            p.chmod(stat.S_IWRITE | stat.S_IREAD)
            p.unlink()
        except Exception:
            raise  # Raise the retry exception instead of the original PermissionError


def _on_rm_error(func, path, exc_info):  # type: ignore[no-untyped-def]
    """shutil.rmtree onerror: clear read-only flag and retry."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except Exception:
        logger.warning("tools step failed", exc_info=True)


def _classify_error(exc: Exception) -> str:
    """Infer a short error description from an exception."""
    import errno as _errno
    name = type(exc).__name__
    msg = str(exc)
    if isinstance(exc, PermissionError):
        if hasattr(exc, "winerror"):
            winerr = getattr(exc, "winerror", 0)
            if winerr == 5:
                return f"[{name}] Access denied -- another process may be using this file"
            if winerr == 32:
                return f"[{name}] File in use by another process"
        return f"[{name}] {msg}"
    if isinstance(exc, FileNotFoundError):
        return f"[{name}] File disappeared before deletion"
    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) == _errno.ENAMETOOLONG:
            return f"[{name}] Path too long (>260 chars)"
        return f"[{name}] {msg}"
    return f"[{name}] {msg}"


def execute_archive_cleanup(
    actions: list[dict[str, str]],
) -> dict[str, Any]:
    """Execute cleanup actions.

    Each action: ``{"archive_path": "...", "folder_path": "...", "action": "delete_archive"|"delete_folder"|"skip"}``

    Returns ``{"deleted_archives": N, "deleted_folders": M, "skipped": K, "errors": [...]}``
    """
    deleted_archives = 0
    deleted_folders = 0
    skipped = 0
    errors: list[str] = []
    deleted_paths: list[str] = []  # Successfully deleted paths (for frontend removal)

    for item in actions:
        action = item.get("action", "skip")
        archive_path = item.get("archive_path", "")
        folder_path = item.get("folder_path", "")

        if action == "skip":
            skipped += 1
            continue

        if action == "delete_archive":
            try:
                p = Path(archive_path)
                if p.is_file():
                    _force_unlink(p)
                    deleted_archives += 1
                    deleted_paths.append(archive_path)
                    logger.info("Deleted archive: %s", archive_path)
                else:
                    if len(errors) < _MAX_ERRORS:
                        errors.append(f"Archive not found: {archive_path}")
            except Exception as exc:
                if len(errors) < _MAX_ERRORS:
                    reason = _classify_error(exc)
                    errors.append(f"{archive_path}: {reason}")

        elif action == "delete_folder":
            try:
                p = Path(folder_path)
                if p.is_dir():
                    shutil.rmtree(p, onerror=_on_rm_error)
                    deleted_folders += 1
                    deleted_paths.append(folder_path)
                    logger.info("Deleted folder: %s", folder_path)
                else:
                    if len(errors) < _MAX_ERRORS:
                        errors.append(f"Folder not found: {folder_path}")
            except Exception as exc:
                if len(errors) < _MAX_ERRORS:
                    reason = _classify_error(exc)
                    errors.append(f"{folder_path}: {reason}")
        else:
            skipped += 1

    return {
        "deleted_archives": deleted_archives,
        "deleted_folders": deleted_folders,
        "skipped": skipped,
        "errors": errors,
        "deleted_paths": deleted_paths,
    }
