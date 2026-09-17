"""Batch ZIP read and info operations.

Handles reading multiple entries from a ZIP with serial and parallel
decompression support.
"""

import contextlib
import datetime as _dt
import io
import logging
import math
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.infra_core.timeout import ARCHIVE_MAX_BATCH_BYTES, ARCHIVE_MAX_ENTRY_SIZE

from .zip_path_resolve import _resolve_entry_name
from .zip_read_single import _is_nested_zip_path, _read_zip_entry_checked, _resolve_zip_info

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parallel batch read configuration
# ---------------------------------------------------------------------------
_PARALLEL_READ_THRESHOLD = 16
_MAX_READ_WORKERS = min(os.cpu_count() or 2, 4)


def batch_zip_info(
    zip_path: str, internal_paths: list[str]
) -> dict[str, tuple[int, int]]:
    """Get mtime and size for multiple entries in a single ZIP open.

    Returns dict mapping internal_path -> (mtime, size).
    Entries that fail resolution are silently skipped.
    """
    result: dict[str, tuple[int, int]] = {}
    # Separate nested ZIP paths for individual processing
    nested_paths = [ip for ip in internal_paths if _is_nested_zip_path(ip)]
    flat_paths = [ip for ip in internal_paths if not _is_nested_zip_path(ip)]

    # Nested ZIP: open inner ZIP for info retrieval
    # Group by inner ZIP to avoid opening the same one multiple times
    nested_groups: dict[str, list[str]] = {}
    for ip in nested_paths:
        inner_zip, inner_file = ip.split("!", 1)
        nested_groups.setdefault(inner_zip, []).append((ip, inner_file))
    for inner_zip_name, entries in nested_groups.items():
        try:
            with zipfile.ZipFile(zip_path, "r") as outer_zf, zipfile.ZipFile(
                io.BytesIO(_read_zip_entry_checked(outer_zf, inner_zip_name, ARCHIVE_MAX_ENTRY_SIZE)),
                "r",
            ) as inner_zf:
                for ip, inner_file in entries:
                    try:
                        _, info = _resolve_zip_info(inner_zf, inner_file)
                        dt = _dt.datetime(*info.date_time)  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
                        result[ip] = (int(dt.timestamp()), info.file_size)
                    except Exception:
                        logger.debug("zip stat failed for %s", ip, exc_info=True)
        except Exception:
            # Loses every entry in this inner archive at once.
            logger.warning(
                "could not open inner archive %s in %s",
                inner_zip_name, zip_path, exc_info=True,
            )

    # Regular flat entries
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for ip in flat_paths:
                try:
                    resolved = _resolve_entry_name(zf, ip)
                    info = zf.getinfo(resolved)
                    dt = _dt.datetime(*info.date_time)  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
                    result[ip] = (int(dt.timestamp()), info.file_size)
                except Exception:
                    logger.debug("zip stat failed for %s", ip, exc_info=True)
    except Exception:
        fallback_mtime = int(os.path.getmtime(zip_path)) if os.path.exists(zip_path) else 0
        for ip in flat_paths:
            if ip not in result:
                result[ip] = (fallback_mtime, 0)
    return result


# ---------------------------------------------------------------------------
# Batch read -- serial + parallel
# ---------------------------------------------------------------------------

def _read_entries_chunk(
    zip_path: str, internal_paths: list[str],
    max_entry_size: int = ARCHIVE_MAX_ENTRY_SIZE,
    budget: int | None = None,
) -> dict[str, bytes]:
    """Read entries from ZIP. Thread-safe: opens ZIP independently.

    Used both as serial fallback and as parallel worker.
    Stops when accumulated bytes exceed *budget*.
    """
    result: dict[str, bytes] = {}
    accumulated = 0

    # Separate nested ZIP paths
    nested_paths = [ip for ip in internal_paths if _is_nested_zip_path(ip)]
    flat_paths = [ip for ip in internal_paths if not _is_nested_zip_path(ip)]

    # Read nested ZIP entries (grouped by inner ZIP)
    nested_groups: dict[str, list[str]] = {}
    for ip in nested_paths:
        inner_zip, inner_file = ip.split("!", 1)
        nested_groups.setdefault(inner_zip, []).append((ip, inner_file))
    for inner_zip_name, entries in nested_groups.items():
        try:
            with zipfile.ZipFile(zip_path, "r") as outer_zf, zipfile.ZipFile(
                io.BytesIO(_read_zip_entry_checked(outer_zf, inner_zip_name, max_entry_size)),
                "r",
            ) as inner_zf:
                for ip, inner_file in entries:
                    try:
                        resolved, info = _resolve_zip_info(inner_zf, inner_file)
                        if info.flag_bits & 0x1:
                            continue
                        if max_entry_size and info.file_size > max_entry_size:
                            logger.warning(
                                "Skipping oversized nested ZIP entry: %s (%d MB)",
                                ip, info.file_size // (1024 * 1024),
                            )
                            continue
                        if budget is not None and accumulated + info.file_size > budget:
                            logger.warning(
                                "Batch read budget exceeded at %d MB, stopping",
                                accumulated // (1024 * 1024),
                            )
                            return result
                        data = inner_zf.read(resolved)
                        result[ip] = data
                        accumulated += len(data)
                    except Exception:
                        logger.debug("zip read failed for %s", ip, exc_info=True)
        except Exception:
            logger.warning(
                "could not open inner archive %s in %s",
                inner_zip_name, zip_path, exc_info=True,
            )

    # Regular flat entries
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for ip in flat_paths:
                try:
                    resolved = _resolve_entry_name(zf, ip)
                    info = zf.getinfo(resolved)
                    if info.flag_bits & 0x1:
                        continue
                    # Size check
                    if max_entry_size and info.file_size > max_entry_size:
                        logger.warning(
                            "Skipping oversized ZIP entry: %s (%d MB)",
                            ip, info.file_size // (1024 * 1024),
                        )
                        continue
                    # Memory budget check
                    if budget is not None and accumulated + info.file_size > budget:
                        logger.warning(
                            "Batch read budget exceeded at %d MB, stopping",
                            accumulated // (1024 * 1024),
                        )
                        break
                    data = zf.read(resolved)
                    result[ip] = data
                    accumulated += len(data)
                except Exception:
                    logger.debug("zip read failed for %s", ip, exc_info=True)
    except Exception:
        # Every flat entry is lost, and the caller sees an empty result rather
        # than an error.
        logger.warning("could not open archive %s", zip_path, exc_info=True)
    return result


def batch_read_from_zip(
    zip_path: str, internal_paths: list[str],
    max_total_bytes: int = ARCHIVE_MAX_BATCH_BYTES,
) -> dict[str, bytes]:
    """Read bytes for multiple entries from a ZIP.

    Small batches are read serially. Large batches (>= threshold) use
    ThreadPoolExecutor for parallel decompression. With isal installed,
    the GIL is released during DEFLATE, enabling true multi-core speedup.

    Stops reading when *max_total_bytes* is exceeded.
    """
    if len(internal_paths) < _PARALLEL_READ_THRESHOLD:
        return _read_entries_chunk(zip_path, internal_paths, budget=max_total_bytes)

    n_workers = min(_MAX_READ_WORKERS, max(2, len(internal_paths) // 4))
    chunk_size = math.ceil(len(internal_paths) / n_workers)
    chunks = [
        internal_paths[i : i + chunk_size]
        for i in range(0, len(internal_paths), chunk_size)
    ]

    # Distribute budget evenly across workers
    per_worker_budget = max_total_bytes // max(n_workers, 1)

    try:
        result: dict[str, bytes] = {}
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = [
                pool.submit(
                    _read_entries_chunk, zip_path, chunk,
                    budget=per_worker_budget,
                )
                for chunk in chunks
            ]
            for future in as_completed(futures):
                with contextlib.suppress(Exception):
                    result.update(future.result(timeout=120))
        return result
    except Exception:
        # Pool failed -- fall back to serial
        return _read_entries_chunk(zip_path, internal_paths, budget=max_total_bytes)
