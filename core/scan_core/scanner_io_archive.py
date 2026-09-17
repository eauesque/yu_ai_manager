"""Archive enumeration and cache helpers for scanner I/O.

Provides iter_files_with_zips() which enumerates regular files and
images inside ZIP/7z/RAR archives in a single directory traversal.
"""

import logging
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from core.rar_core.rar_support import list_images_in_rar
from core.rar_core.rar_support_core import batch_rar_info
from core.sevenz_core.sevenz_support import list_images_in_7z
from core.sevenz_core.sevenz_support_core import batch_7z_info
from core.zip_core.zip_listing import list_images_in_zip
from core.zip_core.zip_support_core import batch_zip_info

from .scanner_io_files import ErrorCallback, _is_excluded

logger = logging.getLogger(__name__)


def iter_files_with_zips(
    root: Path,
    recursive: bool,
    exts: Sequence[str],
    scan_zips: bool = False,
    exclude_dirs: Sequence[str] = (),
    stop_event=None,
    on_archive: Callable[[str], None] | None = None,
    on_error: ErrorCallback = None,
    archive_cache: object | None = None,
) -> Iterable[Path | str]:
    """Enumerate regular files and images inside archives (ZIP/7z/RAR).

    I/O optimisation: rglob("*") runs only once, classifying entries
    by extension into regular files, ZIP, 7z, and RAR buckets.

    *on_archive* is an optional callback invoked with the archive path
    string just before listing its contents.

    *on_error* is called with ``(path, error_type, detail)`` for every
    file or archive that cannot be processed.
    """
    exclude_set = frozenset(exclude_dirs) if exclude_dirs else frozenset()
    ext_set = frozenset(exts)
    _count = 0
    _CHECK_INTERVAL = 500

    # Collect archive paths (processed later only when scan_zips is enabled)
    zip_paths: list[Path] = []
    sevenz_paths: list[Path] = []
    rar_paths: list[Path] = []

    try:
        path_iter = root.rglob("*") if recursive else root.glob("*")
        for p in path_iter:
            if stop_event is not None:
                _count += 1
                if _count % _CHECK_INTERVAL == 0 and stop_event.is_set():
                    return
            try:
                if exclude_set and _is_excluded(p, root, exclude_set):
                    continue
                if not p.is_file():
                    continue
                suffix = p.suffix.lower()
                if suffix == ".zip" and scan_zips:
                    zip_paths.append(p)
                elif suffix == ".7z" and scan_zips:
                    sevenz_paths.append(p)
                elif suffix == ".rar" and scan_zips:
                    rar_paths.append(p)
                elif suffix in ext_set:
                    yield p
            except (PermissionError, OSError) as e:
                if on_error is not None:
                    on_error(str(p), "filesystem", str(e))
                continue
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory {root}: {e}")
        if on_error is not None:
            on_error(str(root), "filesystem", f"Cannot access directory: {e}")

    if not scan_zips:
        return

    # Prune stale cache entries for archives no longer on disk
    if archive_cache is not None:
        all_archive_paths = {str(p) for p in zip_paths} | {str(p) for p in sevenz_paths} | {str(p) for p in rar_paths}
        archive_cache.remove_stale(all_archive_paths)

    ext_tuple = tuple(exts)

    # ZIP archives
    for zip_path in zip_paths:
        if stop_event is not None and stop_event.is_set():
            return
        if on_archive is not None:
            on_archive(str(zip_path))
        try:
            cached = _get_cached_listing(archive_cache, zip_path)
            if cached is not None:
                for internal_path in cached:
                    yield f"{zip_path}!{internal_path}"
                continue
            internal_images = list_images_in_zip(str(zip_path), ext_tuple)
            members_info = _collect_zip_members_info(str(zip_path), internal_images)
            _update_cache(archive_cache, zip_path, internal_images, members_info)
            for internal_path in internal_images:
                yield f"{zip_path}!{internal_path}"
        except Exception as e:
            logger.warning(f"Failed to scan ZIP: {zip_path}: {type(e).__name__}: {e}")
            if on_error is not None:
                on_error(str(zip_path), "encoding", f"{type(e).__name__}: {e}")

    # 7z archives
    for sevenz_path in sevenz_paths:
        if stop_event is not None and stop_event.is_set():
            return
        if on_archive is not None:
            on_archive(str(sevenz_path))
        try:
            cached = _get_cached_listing(archive_cache, sevenz_path)
            if cached is not None:
                for internal_path in cached:
                    yield f"{sevenz_path}!{internal_path}"
                continue
            internal_images = list_images_in_7z(str(sevenz_path), ext_tuple)
            members_info = _collect_7z_members_info(str(sevenz_path), internal_images)
            _update_cache(archive_cache, sevenz_path, internal_images, members_info)
            for internal_path in internal_images:
                yield f"{sevenz_path}!{internal_path}"
        except Exception as e:
            logger.warning(f"Failed to scan 7z: {sevenz_path}: {type(e).__name__}: {e}")
            if on_error is not None:
                on_error(str(sevenz_path), "encoding", f"{type(e).__name__}: {e}")

    # RAR archives
    for rar_path in rar_paths:
        if stop_event is not None and stop_event.is_set():
            return
        if on_archive is not None:
            on_archive(str(rar_path))
        try:
            cached = _get_cached_listing(archive_cache, rar_path)
            if cached is not None:
                for internal_path in cached:
                    yield f"{rar_path}!{internal_path}"
                continue
            internal_images = list_images_in_rar(str(rar_path), ext_tuple)
            members_info = _collect_rar_members_info(str(rar_path), internal_images)
            _update_cache(archive_cache, rar_path, internal_images, members_info)
            for internal_path in internal_images:
                yield f"{rar_path}!{internal_path}"
        except Exception as e:
            logger.warning(f"Failed to scan RAR: {rar_path}: {type(e).__name__}: {e}")
            if on_error is not None:
                on_error(str(rar_path), "encoding", f"{type(e).__name__}: {e}")


def _get_cached_listing(
    cache: object | None, archive_path: Path
) -> list | None:
    """Check cache for unchanged archive. Returns member list or None."""
    if cache is None:
        return None
    try:
        st = archive_path.stat()
        return cache.get_members(str(archive_path), int(st.st_mtime), st.st_size)
    except OSError:
        return None


def _update_cache(
    cache: object | None,
    archive_path: Path,
    members: list,
    members_info: dict | None = None,
) -> None:
    """Store archive listing in cache after a successful listing."""
    if cache is None:
        return
    try:
        st = archive_path.stat()
        cache.update(
            str(archive_path), int(st.st_mtime), st.st_size,
            members, members_info=members_info,
        )
    except OSError:
        pass


def _collect_zip_members_info(
    zip_path: str, members: list
) -> dict | None:
    """Collect per-member (mtime, size) from a ZIP in one open.

    Returns {member_name: [mtime, size]} or None on failure.
    """
    if not members:
        return {}
    try:
        raw = batch_zip_info(zip_path, members)
        return {k: list(v) for k, v in raw.items()}
    except Exception:
        return None


def _collect_7z_members_info(
    archive_path: str, members: list
) -> dict | None:
    """Collect per-member (mtime, size) from a 7z in one open.

    Returns {member_name: [mtime, size]} or None on failure.
    """
    if not members:
        return {}
    try:
        raw = batch_7z_info(archive_path, members)
        return {k: list(v) for k, v in raw.items()}
    except Exception:
        return None


def _collect_rar_members_info(
    archive_path: str, members: list
) -> dict | None:
    """Collect per-member (mtime, size) from a RAR in one open.

    Returns {member_name: [mtime, size]} or None on failure.
    """
    if not members:
        return {}
    try:
        raw = batch_rar_info(archive_path, members)
        return {k: list(v) for k, v in raw.items()}
    except Exception:
        return None
