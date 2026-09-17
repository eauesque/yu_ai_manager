"""Single-entry ZIP read and info operations.

Handles reading bytes, mtime/size retrieval, and nested ZIP support
for individual entries.
"""

import datetime as _dt
import io
import os
import zipfile
from contextlib import ExitStack

from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE

from .zip_path_resolve import _resolve_entry_name


def read_bytes_from_zip(
    zip_path: str, internal_path: str,
    max_size: int = ARCHIVE_MAX_ENTRY_SIZE,
) -> bytes:
    """Read bytes from a ZIP-internal entry.

    Supports nested ZIPs: if *internal_path* contains ``!``, the path
    is split at the first ``!`` and the outer entry is opened as a ZIP
    to read the inner entry.  e.g. ``inner.zip!path/img.png``.

    Raises ``RuntimeError`` for password-protected entries instead of
    the less specific ``RuntimeError`` from zlib.
    Raises ``ValueError`` if the uncompressed size exceeds *max_size*.
    """
    # Nested ZIP detection: internal_path contains "!" and part before "!" is .zip
    if "!" in internal_path:
        parts = internal_path.split("!", 1)
        if parts[0].lower().endswith(".zip"):
            return _read_nested_zip(zip_path, parts[0], parts[1], max_size)

    with zipfile.ZipFile(zip_path, "r") as zf:
        return _read_zip_entry_checked(zf, internal_path, max_size)


def _read_nested_zip(
    outer_zip_path: str,
    inner_zip_entry: str,
    inner_file_path: str,
    max_size: int,
) -> bytes:
    """Read a file from a nested ZIP (ZIP-in-ZIP)."""
    parts = [inner_zip_entry, *inner_file_path.split("!")]
    with zipfile.ZipFile(outer_zip_path, "r") as outer_zf:
        return _read_nested_parts(outer_zf, parts, max_size)


def get_mtime_and_size_from_zip(zip_path: str, internal_path: str) -> tuple[int, int]:
    """Get mtime and size from a single ZIP open."""
    try:
        # Nested ZIP support
        if "!" in internal_path and internal_path.split("!", 1)[0].lower().endswith(".zip"):
            parts = internal_path.split("!", 1)
            with zipfile.ZipFile(zip_path, "r") as outer_zf:
                with zipfile.ZipFile(
                    io.BytesIO(_read_zip_entry_checked(outer_zf, parts[0], ARCHIVE_MAX_ENTRY_SIZE)),
                    "r",
                ) as inner_zf:
                    resolved, info = _resolve_zip_info(inner_zf, parts[1])
                dt = _dt.datetime(*info.date_time)  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
                return int(dt.timestamp()), info.file_size
        with zipfile.ZipFile(zip_path, "r") as zf:
            resolved = _resolve_entry_name(zf, internal_path)
            info = zf.getinfo(resolved)
            dt = _dt.datetime(*info.date_time)  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
            return int(dt.timestamp()), info.file_size
    except Exception:
        return int(os.path.getmtime(zip_path)), 0


def _is_nested_zip_path(ip: str) -> bool:
    """Return True if *ip* is a nested ZIP internal path like ``inner.zip!file.png``."""
    if "!" not in ip:
        return False
    return ip.split("!", 1)[0].lower().endswith(".zip")


def _nested_zip_info(
    zip_path: str, ip: str,
) -> tuple[int, int]:
    """Get mtime/size for a file inside a nested ZIP."""
    parts = ip.split("!", 1)
    with zipfile.ZipFile(zip_path, "r") as outer_zf:
        with zipfile.ZipFile(
            io.BytesIO(_read_zip_entry_checked(outer_zf, parts[0], ARCHIVE_MAX_ENTRY_SIZE)),
            "r",
        ) as inner_zf:
            resolved, info = _resolve_zip_info(inner_zf, parts[1])
        dt = _dt.datetime(*info.date_time)  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
        return int(dt.timestamp()), info.file_size


def _nested_zip_read(
    zip_path: str, ip: str, max_entry_size: int,
) -> bytes:
    """Read bytes for a file inside a nested ZIP."""
    parts = ip.split("!", 1)
    with zipfile.ZipFile(zip_path, "r") as outer_zf:
        return _read_nested_parts(outer_zf, [parts[0], parts[1]], max_entry_size)


def _resolve_zip_info(zf: zipfile.ZipFile, internal_path: str):
    """Resolve a ZIP entry name and return ``(resolved_name, info)``."""
    resolved = _resolve_entry_name(zf, internal_path)
    return resolved, zf.getinfo(resolved)


def _ensure_zip_entry_safe(info: zipfile.ZipInfo, label: str, max_size: int) -> None:
    """Reject encrypted or oversized ZIP entries."""
    if info.flag_bits & 0x1:
        raise RuntimeError(f"Password-protected entry: {label}")
    if max_size and info.file_size > max_size:
        raise ValueError(
            f"Entry too large: {label} "
            f"({info.file_size / 1024 / 1024:.0f} MB > "
            f"{max_size / 1024 / 1024:.0f} MB limit)"
        )


def _read_zip_entry_checked(
    zf: zipfile.ZipFile,
    internal_path: str,
    max_size: int,
) -> bytes:
    """Read a ZIP entry after encrypted/size checks."""
    resolved, info = _resolve_zip_info(zf, internal_path)
    _ensure_zip_entry_safe(info, internal_path, max_size)
    return zf.read(resolved)


def _open_nested_zip_checked(
    stack: ExitStack,
    zf: zipfile.ZipFile,
    internal_path: str,
    max_size: int,
) -> zipfile.ZipFile:
    """Open an inner ZIP entry after checking its uncompressed size."""
    inner_data = _read_zip_entry_checked(zf, internal_path, max_size)
    return stack.enter_context(zipfile.ZipFile(io.BytesIO(inner_data), "r"))


def _read_nested_parts(
    outer_zf: zipfile.ZipFile,
    parts: list[str],
    max_size: int,
) -> bytes:
    """Read a nested ZIP path represented as ``['a.zip', 'b.zip', 'c.png']``."""
    with ExitStack() as stack:
        current = outer_zf
        for idx, part in enumerate(parts):
            last = idx == len(parts) - 1
            if last:
                return _read_zip_entry_checked(current, part, max_size)
            current = _open_nested_zip_checked(stack, current, part, max_size)
    raise FileNotFoundError("Nested ZIP path could not be resolved")


def get_mtime_from_zip(zip_path: str, internal_path: str) -> int:
    """Get modified time for ZIP entry as Unix timestamp."""
    return get_mtime_and_size_from_zip(zip_path, internal_path)[0]


def get_size_from_zip(zip_path: str, internal_path: str) -> int:
    """Get uncompressed entry size in bytes."""
    return get_mtime_and_size_from_zip(zip_path, internal_path)[1]
