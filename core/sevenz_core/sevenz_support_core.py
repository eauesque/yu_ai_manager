"""7z archive path and I/O helpers.

Uses 7z CLI wrapper (sevenz_cli) instead of py7zr (LGPL).
"""

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

from . import sevenz_cli

logger = logging.getLogger(__name__)


def _sevenz_available() -> bool:
    return sevenz_cli.sevenz_available()


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
    """Resolve an internal path against 7z entry names with Unicode variants."""
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
        f"7z has {len(names)} entries, sample: {sample!r})"
    )
    raise KeyError(detail)


def is_7z_path(path: str) -> tuple[bool, str | None, str | None]:
    """Check whether a path is in 7z entry form ``archive.7z!internal_path``."""
    from core.helpers_core.helpers_text_path import split_archive_path
    if "!" not in path:
        return (False, None, None)

    archive_path, internal_path = split_archive_path(path)

    if not archive_path.lower().endswith(".7z"):
        return (False, None, None)
    if os.path.exists(archive_path):
        return (True, archive_path, internal_path)
    return (False, None, None)


def read_bytes_from_7z(
    archive_path: str, internal_path: str,
    max_size: int = ARCHIVE_MAX_ENTRY_SIZE,
) -> bytes:
    """Read bytes from a 7z-internal entry."""
    if not _sevenz_available():
        raise ImportError("7z CLI is required for 7z support (install 7-Zip)")

    names = sevenz_cli.list_names(archive_path)
    resolved = _resolve_entry_name(names, internal_path)
    return sevenz_cli.read_entry_bytes(archive_path, resolved, max_size=max_size)


def get_mtime_and_size_from_7z(archive_path: str, internal_path: str) -> tuple[int, int]:
    """Get mtime and size from a single 7z archive listing."""
    if not _sevenz_available():
        return int(os.path.getmtime(archive_path)), 0
    try:
        names = sevenz_cli.list_names(archive_path)
        resolved = _resolve_entry_name(names, internal_path)
        return sevenz_cli.get_entry_info(archive_path, resolved)
    except Exception:
        return int(os.path.getmtime(archive_path)), 0


def batch_7z_info(
    archive_path: str, internal_paths: list[str]
) -> dict[str, tuple[int, int]]:
    """Get mtime and size for multiple entries in a single 7z listing."""
    if not _sevenz_available():
        fallback_mtime = int(os.path.getmtime(archive_path)) if os.path.exists(archive_path) else 0
        return {ip: (fallback_mtime, 0) for ip in internal_paths}
    try:
        entries = sevenz_cli.list_entries(archive_path)
        names = [e.filename for e in entries if not e.is_directory]

        resolved_map: dict[str, str] = {}
        for ip in internal_paths:
            with contextlib.suppress(KeyError):
                resolved_map[ip] = _resolve_entry_name(names, ip)

        entry_map = {e.filename: e for e in entries}
        result: dict[str, tuple[int, int]] = {}
        fallback_mtime = int(os.path.getmtime(archive_path)) if os.path.exists(archive_path) else 0

        for ip, resolved in resolved_map.items():
            entry = entry_map.get(resolved)
            if entry:
                mtime = int(entry.modified.timestamp()) if entry.modified else fallback_mtime
                result[ip] = (mtime, entry.size)
            else:
                result[ip] = (fallback_mtime, 0)

        for ip in internal_paths:
            if ip not in result:
                result[ip] = (fallback_mtime, 0)
        return result
    except Exception:
        fallback_mtime = int(os.path.getmtime(archive_path)) if os.path.exists(archive_path) else 0
        return {ip: (fallback_mtime, 0) for ip in internal_paths}


def batch_read_from_7z(
    archive_path: str, internal_paths: list[str],
    max_total_bytes: int = ARCHIVE_MAX_BATCH_BYTES,
) -> dict[str, bytes]:
    """Read bytes for multiple entries using 7z CLI batch extraction."""
    if not _sevenz_available():
        raise ImportError("7z CLI is required for 7z support")

    import tempfile

    entries = sevenz_cli.list_entries(archive_path)
    names = [e.filename for e in entries if not e.is_directory]
    entry_map = {e.filename: e for e in entries}

    resolved_map: dict[str, str] = {}
    for ip in internal_paths:
        with contextlib.suppress(KeyError):
            resolved_map[ip] = _resolve_entry_name(names, ip)
    if not resolved_map:
        return {}

    # Filter out oversized entries
    targets_filtered = []
    for resolved in resolved_map.values():
        entry = entry_map.get(resolved)
        sz = entry.size if entry else 0
        if sz <= ARCHIVE_MAX_ENTRY_SIZE:
            targets_filtered.append(resolved)
        else:
            logger.warning(
                "Skipping oversized 7z entry: %s (%d MB)",
                resolved, sz // (1024 * 1024),
            )

    if not targets_filtered:
        return {}

    reverse_map = {v: k for k, v in resolved_map.items()}
    result: dict[str, bytes] = {}
    accumulated = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        sevenz_cli.extract_to_dir(archive_path, tmpdir, targets=targets_filtered)
        for resolved in targets_filtered:
            ip = reverse_map.get(resolved)
            if ip is None:
                continue
            extracted = os.path.join(tmpdir, resolved.replace("/", os.sep))
            if os.path.exists(extracted):
                try:
                    sz = os.path.getsize(extracted)
                    if accumulated + sz > max_total_bytes:
                        logger.warning(
                            "7z batch read budget exceeded at %d MB",
                            accumulated // (1024 * 1024),
                        )
                        break
                    with open(extracted, "rb") as f:
                        result[ip] = f.read()
                    accumulated += sz
                except Exception:
                    logger.debug("7z entry step failed", exc_info=True)
    return result


def get_mtime_from_7z(archive_path: str, internal_path: str) -> int:
    """Get modified time for 7z entry as Unix timestamp."""
    return get_mtime_and_size_from_7z(archive_path, internal_path)[0]


def get_size_from_7z(archive_path: str, internal_path: str) -> int:
    """Get uncompressed entry size in bytes."""
    return get_mtime_and_size_from_7z(archive_path, internal_path)[1]


def _list_images_in_7z_sync(
    archive_path: str,
    extensions: tuple[str, ...],
) -> list[str]:
    """Synchronous image listing via 7z CLI."""
    if sevenz_cli.needs_password(archive_path):
        logger.debug("7z entry is encrypted, skipping: %s", archive_path)
        return []
    images: list[str] = []
    for entry in sevenz_cli.list_entries(archive_path):
        if entry.is_directory:
            continue
        if entry.filename.lower().endswith(extensions):
            images.append(entry.filename)
    logger.debug("7z listed OK: %s (%d images)", archive_path, len(images))
    return images


def list_images_in_7z(
    archive_path: str,
    extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".svg"),
    timeout: float = ARCHIVE_LIST_TIMEOUT,
) -> list[str]:
    """List image entries in 7z archive with timeout protection."""
    if not _sevenz_available():
        logger.warning("7z CLI not found, skipping 7z: %s", archive_path)
        return []
    try:
        return run_with_timeout(
            lambda: _list_images_in_7z_sync(archive_path, extensions),
            timeout=timeout,
            label=archive_path,
        )
    except TimeoutError:
        logger.warning("7z listing timed out (%.0fs): %s", timeout, archive_path)
    except PermissionError:
        logger.warning("Permission denied for 7z: %s", archive_path)
    except Exception as e:
        logger.warning("Failed to list 7z contents: %s: %s: %s", archive_path, type(e).__name__, e)
    return []
