"""RAR archive path and I/O helpers."""

import contextlib
import logging
import os
import unicodedata

from core.infra_core.encoding import repair_cp437_name
from core.infra_core.timeout import (
    ARCHIVE_LIST_TIMEOUT,
    ARCHIVE_MAX_BATCH_BYTES,
    ARCHIVE_MAX_ENTRY_SIZE,
    run_with_timeout,
)

logger = logging.getLogger(__name__)

try:
    import rarfile
except ImportError:
    rarfile = None  # type: ignore[assignment]


def _rar_available() -> bool:
    return rarfile is not None


def _normalize_separators(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("./")


def _name_variants(name: str) -> list[str]:
    """Generate Unicode normalization + encoding repair variants."""
    base = _normalize_separators(name)
    variants = {base}
    variants.add(unicodedata.normalize("NFC", base))
    variants.add(unicodedata.normalize("NFKC", base))

    for repaired in repair_cp437_name(base):
        repaired_norm = _normalize_separators(repaired)
        variants.add(repaired_norm)
        variants.add(unicodedata.normalize("NFC", repaired_norm))
        variants.add(unicodedata.normalize("NFKC", repaired_norm))
    return [v for v in variants if v]


def _resolve_entry_name(names: list[str], internal_path: str) -> str:
    """Resolve an internal path against RAR entry names with Unicode variants."""
    if internal_path in names:
        return internal_path

    variant_to_actual = {}
    for actual in names:
        for variant in _name_variants(actual):
            variant_to_actual.setdefault(variant, actual)

    for variant in _name_variants(internal_path):
        resolved = variant_to_actual.get(variant)
        if resolved is not None:
            return resolved

    target_name = os.path.basename(_normalize_separators(internal_path))
    if target_name:
        candidates = [n for n in names if os.path.basename(_normalize_separators(n)) == target_name]
        if len(candidates) == 1:
            return candidates[0]

    sample = names[:5]
    detail = (
        f"Entry not found: {internal_path!r} "
        f"(variants tried: {len(_name_variants(internal_path))}, "
        f"RAR has {len(names)} entries, sample: {sample!r})"
    )
    raise KeyError(detail)


def is_rar_path(path: str) -> tuple[bool, str | None, str | None]:
    """Check whether a path is in RAR entry form ``archive.rar!internal_path``."""
    from core.helpers_core.helpers_text_path import split_archive_path
    if "!" not in path:
        return (False, None, None)

    archive_path, internal_path = split_archive_path(path)

    if not archive_path.lower().endswith(".rar"):
        return (False, None, None)
    if os.path.exists(archive_path):
        return (True, archive_path, internal_path)
    return (False, None, None)


def read_bytes_from_rar(
    archive_path: str, internal_path: str,
    max_size: int = ARCHIVE_MAX_ENTRY_SIZE,
) -> bytes:
    """Read bytes from a RAR-internal entry.

    Raises ``ValueError`` if the uncompressed size exceeds *max_size*.
    """
    if not _rar_available():
        raise ImportError("rarfile is required for RAR support (pip install rarfile)")

    with rarfile.RarFile(archive_path, "r") as rf:
        names = rf.namelist()
        resolved = _resolve_entry_name(names, internal_path)
        if max_size:
            info = rf.getinfo(resolved)
            if info.file_size and info.file_size > max_size:
                raise ValueError(
                    f"Entry too large: {internal_path} "
                    f"({info.file_size / 1024 / 1024:.0f} MB > "
                    f"{max_size / 1024 / 1024:.0f} MB limit)"
                )
        return rf.read(resolved)


def get_mtime_and_size_from_rar(archive_path: str, internal_path: str) -> tuple[int, int]:
    """Get mtime and size from a single RAR archive open."""
    if not _rar_available():
        return int(os.path.getmtime(archive_path)), 0
    try:
        with rarfile.RarFile(archive_path, "r") as rf:
            names = rf.namelist()
            resolved = _resolve_entry_name(names, internal_path)
            info = rf.getinfo(resolved)
            mtime = int(info.date_time and _datetime_tuple_to_ts(info.date_time) or os.path.getmtime(archive_path))
            size = info.file_size or 0
            return mtime, size
        return int(os.path.getmtime(archive_path)), 0
    except Exception:
        return int(os.path.getmtime(archive_path)), 0


def _datetime_tuple_to_ts(dt_tuple: tuple) -> float:
    """Convert RAR date_time tuple (y,m,d,h,m,s) to Unix timestamp."""
    import datetime as _dt
    try:
        return _dt.datetime(*dt_tuple).timestamp()  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
    except (ValueError, TypeError, OSError):
        return 0.0


def batch_rar_info(
    archive_path: str, internal_paths: list[str]
) -> dict[str, tuple[int, int]]:
    """Get mtime and size for multiple entries in a single RAR open.

    Returns dict mapping internal_path -> (mtime, size).
    """
    result: dict[str, tuple[int, int]] = {}
    if not _rar_available():
        fallback_mtime = int(os.path.getmtime(archive_path)) if os.path.exists(archive_path) else 0
        return {ip: (fallback_mtime, 0) for ip in internal_paths}
    try:
        with rarfile.RarFile(archive_path, "r") as rf:
            names = rf.namelist()
            resolved_map: dict[str, str] = {}
            for ip in internal_paths:
                with contextlib.suppress(KeyError):
                    resolved_map[ip] = _resolve_entry_name(names, ip)
            reverse_map = {v: k for k, v in resolved_map.items()}
            for info in rf.infolist():
                ip = reverse_map.get(info.filename)
                if ip is not None:
                    mtime = int(_datetime_tuple_to_ts(info.date_time)) if info.date_time else int(os.path.getmtime(archive_path))
                    size = info.file_size or 0
                    result[ip] = (mtime, size)
    except Exception:
        fallback_mtime = int(os.path.getmtime(archive_path)) if os.path.exists(archive_path) else 0
        for ip in internal_paths:
            if ip not in result:
                result[ip] = (fallback_mtime, 0)
    return result


def batch_read_from_rar(
    archive_path: str, internal_paths: list[str],
    max_total_bytes: int = ARCHIVE_MAX_BATCH_BYTES,
) -> dict[str, bytes]:
    """Read bytes for multiple entries in a single RAR open.

    Returns dict mapping internal_path -> file_bytes.
    Stops reading once *max_total_bytes* is exceeded.
    """
    if not _rar_available():
        raise ImportError("rarfile is required for RAR support")
    result: dict[str, bytes] = {}
    accumulated = 0
    with rarfile.RarFile(archive_path, "r") as rf:
        names = rf.namelist()
        resolved_map: dict[str, str] = {}
        for ip in internal_paths:
            with contextlib.suppress(KeyError):
                resolved_map[ip] = _resolve_entry_name(names, ip)
        for ip, resolved in resolved_map.items():
            try:
                info = rf.getinfo(resolved)
                entry_size = info.file_size or 0
                # Individual size check
                if entry_size > ARCHIVE_MAX_ENTRY_SIZE:
                    logger.warning(
                        "Skipping oversized RAR entry: %s (%d MB)",
                        ip, entry_size // (1024 * 1024),
                    )
                    continue
                # Memory budget check
                if accumulated + entry_size > max_total_bytes:
                    logger.warning(
                        "RAR batch read budget exceeded at %d MB",
                        accumulated // (1024 * 1024),
                    )
                    break
                data = rf.read(resolved)
                result[ip] = data
                accumulated += len(data)
            except Exception:
                logger.warning("step failed", exc_info=True)
    return result


def get_mtime_from_rar(archive_path: str, internal_path: str) -> int:
    """Get modified time for RAR entry as Unix timestamp."""
    return get_mtime_and_size_from_rar(archive_path, internal_path)[0]


def get_size_from_rar(archive_path: str, internal_path: str) -> int:
    """Get uncompressed entry size in bytes."""
    return get_mtime_and_size_from_rar(archive_path, internal_path)[1]


def _list_images_in_rar_sync(
    archive_path: str,
    extensions: tuple[str, ...],
) -> list[str]:
    """Synchronous image listing -- called inside timeout wrapper."""
    images: list[str] = []
    with rarfile.RarFile(archive_path, "r") as rf:
        for info in rf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.lower().endswith(extensions):
                images.append(name)
    logger.debug("RAR listed OK: %s (%d images)", archive_path, len(images))
    return images


def list_images_in_rar(
    archive_path: str,
    extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".svg"),
    timeout: float = ARCHIVE_LIST_TIMEOUT,
) -> list[str]:
    """List image entries in RAR archive with timeout protection."""
    if not _rar_available():
        logger.warning(f"rarfile not installed, skipping RAR: {archive_path}")
        return []
    try:
        return run_with_timeout(
            lambda: _list_images_in_rar_sync(archive_path, extensions),
            timeout=timeout,
            label=archive_path,
        )
    except TimeoutError:
        logger.warning(f"RAR listing timed out ({timeout}s): {archive_path}")
    except PermissionError:
        logger.warning(f"Permission denied for RAR: {archive_path}")
    except Exception as e:
        logger.warning(f"Failed to list RAR contents: {archive_path}: {type(e).__name__}: {e}")
    return []
