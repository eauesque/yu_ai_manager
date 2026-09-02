"""Archive-specific thumbnail warmup functions.

Handles batch thumbnail generation for ZIP, 7z, and RAR archives
by opening each archive once and processing all members together.
"""

import io
import logging
import threading
from pathlib import Path

from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE

logger = logging.getLogger(__name__)


def _warmup_zip(
    archive_path: str,
    members: list[tuple[int, str, str, object]],  # (file_id, inner_path, full_path, mtime)
    cache_dir: Path,
) -> int:
    """Open a ZIP once and generate thumbnails for all members."""
    import zipfile

    from PIL import Image

    from .media import resolve_zip_target
    from .thumbnail_batch_warmup_core import (
        _archive_done_cv_lock,
        _archive_done_cvs,
        _cleanup_archive_lock,
        _get_archive_lock,
    )
    from .thumbnail_common import cache_path_for_source, save_image_thumbnail, vips_thumbnail_from_buffer

    with _archive_done_cv_lock:
        _archive_done_cvs[archive_path] = threading.Condition()

    lock = _get_archive_lock(archive_path)
    if not lock.acquire(timeout=30):
        logger.warning("Warmup lock timeout for ZIP: %s", archive_path)
        with _archive_done_cv_lock:
            cv = _archive_done_cvs.pop(archive_path, None)
        if cv is not None:
            with cv:
                cv.notify_all()
        _cleanup_archive_lock(archive_path)
        return 0

    count = 0
    try:
        zip_path = Path(archive_path)
        if not zip_path.exists():
            return 0

        # Separate nested paths (inner.zip!file.jpg format)
        nested_members = []
        flat_members = []
        for m in members:
            inner_path = m[1]
            if "!" in inner_path and inner_path.split("!", 1)[0].lower().endswith(".zip"):
                nested_members.append(m)
            else:
                flat_members.append(m)

        # Regular flat entries
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()

            for _file_id, inner_path, full_path, mtime in flat_members:
                try:
                    cp = cache_path_for_source(cache_dir, full_path, mtime)
                    if cp.exists():
                        continue

                    target = resolve_zip_target(namelist, inner_path)
                    if not target:
                        continue

                    with zf.open(target) as f:
                        data = f.read()

                    if vips_thumbnail_from_buffer(data, cp):
                        count += 1
                        continue

                    img = Image.open(io.BytesIO(data))
                    save_image_thumbnail(img, cp, Image)
                    count += 1
                except Exception as exc:
                    logger.debug("ZIP warmup skip %s: %s", inner_path, exc)

        # Nested ZIP entries: group by inner ZIP
        nested_groups: dict[str, list] = {}
        for m in nested_members:
            inner_zip_name = m[1].split("!", 1)[0]
            nested_groups.setdefault(inner_zip_name, []).append(m)

        for inner_zip_name, group in nested_groups.items():
            try:
                with zipfile.ZipFile(zip_path, "r") as outer_zf:
                    from core.zip_core.zip_read_single import _read_zip_entry_checked
                    with zipfile.ZipFile(
                        io.BytesIO(_read_zip_entry_checked(outer_zf, inner_zip_name, ARCHIVE_MAX_ENTRY_SIZE)),
                        "r",
                    ) as inner_zf:
                        inner_namelist = inner_zf.namelist()
                        for _file_id, inner_path, full_path, mtime in group:
                            try:
                                cp = cache_path_for_source(cache_dir, full_path, mtime)
                                if cp.exists():
                                    continue
                                nested_file = inner_path.split("!", 1)[1]
                                target = resolve_zip_target(inner_namelist, nested_file)
                                if not target:
                                    continue
                                with inner_zf.open(target) as f:
                                    data = f.read()
                                if vips_thumbnail_from_buffer(data, cp):
                                    count += 1
                                    continue
                                img = Image.open(io.BytesIO(data))
                                save_image_thumbnail(img, cp, Image)
                                count += 1
                            except Exception as exc:
                                logger.debug("Nested ZIP warmup skip %s: %s", inner_path, exc)
            except Exception as exc:
                logger.debug("Cannot open nested ZIP %s: %s", inner_zip_name, exc)
    finally:
        lock.release()
        _cleanup_archive_lock(archive_path)
        with _archive_done_cv_lock:
            _cv = _archive_done_cvs.pop(archive_path, None)
        if _cv is not None:
            with _cv:
                _cv.notify_all()

    logger.info("ZIP batch warmup: %s -> %d/%d thumbnails", archive_path, count, len(members))
    return count


def _warmup_7z(
    archive_path: str,
    members: list[tuple[int, str, str, object]],  # (file_id, inner_path, full_path, mtime)
    cache_dir: Path,
) -> int:
    """Open a 7z once and generate thumbnails for all members."""
    from PIL import Image

    from core.sevenz_core.sevenz_support_core import batch_read_from_7z

    from .thumbnail_batch_warmup_core import (
        _archive_done_cv_lock,
        _archive_done_cvs,
        _cleanup_archive_lock,
        _get_archive_lock,
    )
    from .thumbnail_common import cache_path_for_source, save_image_thumbnail, vips_thumbnail_from_buffer

    with _archive_done_cv_lock:
        _archive_done_cvs[archive_path] = threading.Condition()

    lock = _get_archive_lock(archive_path)
    if not lock.acquire(timeout=120):  # Longer timeout since 7z is slow
        logger.warning("Warmup lock timeout for 7z: %s", archive_path)
        with _archive_done_cv_lock:
            cv = _archive_done_cvs.pop(archive_path, None)
        if cv is not None:
            with cv:
                cv.notify_all()
        _cleanup_archive_lock(archive_path)
        return 0

    count = 0
    try:
        if not Path(archive_path).exists():
            return 0

        inner_paths = [ip for _, ip, _, _ in members]
        # Extract all files in a single 7z open
        data_map = batch_read_from_7z(archive_path, inner_paths)

        for _file_id, inner_path, full_path, mtime in members:
            try:
                cp = cache_path_for_source(cache_dir, full_path, mtime)
                if cp.exists():
                    continue

                data = data_map.get(inner_path)
                if not data:
                    continue

                if vips_thumbnail_from_buffer(data, cp):
                    count += 1
                    continue

                img = Image.open(io.BytesIO(data))
                save_image_thumbnail(img, cp, Image)
                count += 1
            except Exception as exc:
                logger.debug("7z warmup skip %s: %s", inner_path, exc)
    finally:
        lock.release()
        _cleanup_archive_lock(archive_path)
        with _archive_done_cv_lock:
            _cv = _archive_done_cvs.pop(archive_path, None)
        if _cv is not None:
            with _cv:
                _cv.notify_all()

    logger.info("7z batch warmup: %s -> %d/%d thumbnails", archive_path, count, len(members))
    return count


def _warmup_rar(
    archive_path: str,
    members: list[tuple[int, str, str, object]],
    cache_dir: Path,
) -> int:
    """Open a RAR once and generate thumbnails for all members."""
    from PIL import Image

    from core.rar_core.rar_support_core import batch_read_from_rar

    from .thumbnail_batch_warmup_core import (
        _archive_done_cv_lock,
        _archive_done_cvs,
        _cleanup_archive_lock,
        _get_archive_lock,
    )
    from .thumbnail_common import cache_path_for_source, save_image_thumbnail, vips_thumbnail_from_buffer

    with _archive_done_cv_lock:
        _archive_done_cvs[archive_path] = threading.Condition()

    lock = _get_archive_lock(archive_path)
    if not lock.acquire(timeout=120):
        logger.warning("Warmup lock timeout for RAR: %s", archive_path)
        with _archive_done_cv_lock:
            cv = _archive_done_cvs.pop(archive_path, None)
        if cv is not None:
            with cv:
                cv.notify_all()
        _cleanup_archive_lock(archive_path)
        return 0

    count = 0
    try:
        if not Path(archive_path).exists():
            return 0

        inner_paths = [ip for _, ip, _, _ in members]
        data_map = batch_read_from_rar(archive_path, inner_paths)

        for _file_id, inner_path, full_path, mtime in members:
            try:
                cp = cache_path_for_source(cache_dir, full_path, mtime)
                if cp.exists():
                    continue

                data = data_map.get(inner_path)
                if not data:
                    continue

                if vips_thumbnail_from_buffer(data, cp):
                    count += 1
                    continue

                img = Image.open(io.BytesIO(data))
                save_image_thumbnail(img, cp, Image)
                count += 1
            except Exception as exc:
                logger.debug("RAR warmup skip %s: %s", inner_path, exc)
    finally:
        lock.release()
        _cleanup_archive_lock(archive_path)
        with _archive_done_cv_lock:
            _cv = _archive_done_cvs.pop(archive_path, None)
        if _cv is not None:
            with _cv:
                _cv.notify_all()

    logger.info("RAR batch warmup: %s -> %d/%d thumbnails", archive_path, count, len(members))
    return count
