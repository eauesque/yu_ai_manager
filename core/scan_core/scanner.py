"""Compatibility entrypoint for scanner APIs."""

import sqlite3
from pathlib import Path
from typing import Any

from core.helpers_core.helpers_text_path import archive_part, is_archive_member
from core.scan.rar_worker_batch import scan_batch_rar
from core.scan.rar_worker_single import scan_one_rar
from core.scan.sevenz_worker_batch import scan_batch_7z
from core.scan.sevenz_worker_single import scan_one_7z
from core.scan.zip_worker_batch import scan_batch_zip
from core.scan.zip_worker_single import scan_one_zip

from .scanner_io import iter_files, iter_files_with_zips
from .scanner_regular import scan_one_regular
from .scanner_state import set_extension_manager

# ("added"|"updated", file_id) or None (skipped)
ScanResult = tuple[str, int] | None


def _is_7z_archive_path(path: str) -> bool:
    """Check if an archive!entry path refers to a .7z archive."""
    return archive_part(path).lower().endswith(".7z")


def _is_rar_archive_path(path: str) -> bool:
    """Check if an archive!entry path refers to a .rar archive."""
    return archive_part(path).lower().endswith(".rar")


def scan_one(con: sqlite3.Connection, p: Path | str, config: dict[str, Any], force: bool, compute_hash: bool, *, skip_backfill: bool = False) -> ScanResult:
    if isinstance(p, str) and is_archive_member(p):
        if _is_7z_archive_path(p):
            return scan_one_7z(con, p, config, force, skip_backfill=skip_backfill)
        elif _is_rar_archive_path(p):
            return scan_one_rar(con, p, config, force, skip_backfill=skip_backfill)
        else:
            return scan_one_zip(con, p, config, force, skip_backfill=skip_backfill)
    return scan_one_regular(con, p, config, force, compute_hash, skip_backfill=skip_backfill)


def scan_batch(con, archive_path: str, internal_paths: list, config, force: bool, compute_hash: bool, *, skip_backfill: bool = False, archive_cache=None):
    """Batch-scan multiple entries in a single archive.

    Returns list of ScanResult (one per internal_path, same order).
    """
    if archive_path.lower().endswith(".7z"):
        return scan_batch_7z(con, archive_path, internal_paths, config, force, skip_backfill=skip_backfill, archive_cache=archive_cache)
    elif archive_path.lower().endswith(".rar"):
        return scan_batch_rar(con, archive_path, internal_paths, config, force, skip_backfill=skip_backfill, archive_cache=archive_cache)
    else:
        return scan_batch_zip(con, archive_path, internal_paths, config, force, skip_backfill=skip_backfill, archive_cache=archive_cache)


__all__ = [
    "set_extension_manager",
    "scan_batch",
    "scan_one",
    "scan_one_regular",
    "iter_files",
    "iter_files_with_zips",
]
