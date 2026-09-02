"""Build a ZIP from a list of file IDs.

Framework-free: no Flask dependency, reusable by desktop frontends.
Pattern borrowed from ``favorites_export.export_favorites_zip_bytes()``.
"""

import logging
import os
import tempfile
import time
import zipfile

from core.helpers_core.archive_zip_copy import (
    get_archive_member_size,
    write_archive_member_to_zip,
)
from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path
from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE, ARCHIVE_MAX_EXPORT_BYTES

logger = logging.getLogger(__name__)

_SPOOL_MAX_MEMORY = 16 * 1024 * 1024  # 16 MB before spilling ZIP output to disk
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def build_batch_zip_filename() -> str:
    """Return a timestamped ZIP filename for batch download."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"batch_{ts}.zip"


def open_batch_zip_stream(con, file_ids: list[int]):
    """Build a ZIP stream of the requested files.

    Returns ``(zip_file, file_count)`` where *zip_file* is positioned at the
    start and *file_count* is the number of files actually added. Returns
    ``(None, 0)`` when there is nothing to export.

    合計サイズが ARCHIVE_MAX_EXPORT_BYTES を超えた場合は
    それ以上のファイル追加を中断する。
    """
    if not file_ids:
        return None, 0

    unique_file_ids = list(dict.fromkeys(file_ids))
    path_by_id: dict[int, str] = {}
    for chunk in _chunks(unique_file_ids):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
            chunk,
        )
        path_by_id.update({int(row[0]): row[1] for row in cursor})

    buf = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY, mode="w+b")  # noqa: SIM115 — intentional: file lives beyond context
    count = 0
    accumulated = 0
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            used_names: set[str] = set()
            for file_id in unique_file_ids:
                path = path_by_id.get(file_id)
                if not path:
                    continue
                try:
                    if is_archive_member(path):
                        arc_path, internal = split_archive_path(path)
                        entry_size = get_archive_member_size(arc_path, internal)
                        if entry_size > ARCHIVE_MAX_ENTRY_SIZE:
                            logger.warning(
                                "Skipping oversized archive member in batch: %s!%s (%d MB)",
                                arc_path, internal, entry_size // (1024 * 1024),
                            )
                            continue
                        arcname = os.path.basename(internal)
                    elif os.path.isfile(path):
                        entry_size = os.path.getsize(path)
                        if entry_size > ARCHIVE_MAX_ENTRY_SIZE:
                            logger.warning(
                                "Skipping oversized file in batch: %s (%d MB)",
                                path, entry_size // (1024 * 1024),
                            )
                            continue
                        arcname = os.path.basename(path)
                    else:
                        continue

                    if accumulated + entry_size > ARCHIVE_MAX_EXPORT_BYTES:
                        logger.warning(
                            "Batch ZIP size limit reached at %d MB, stopping",
                            accumulated // (1024 * 1024),
                        )
                        break

                    base_name = arcname
                    counter = 2
                    while arcname in used_names:
                        name_part, ext = os.path.splitext(base_name)
                        arcname = f"{name_part}_{counter}{ext}"
                        counter += 1
                    used_names.add(arcname)

                    if is_archive_member(path):
                        write_archive_member_to_zip(zf, arcname, arc_path, internal)
                    else:
                        zf.write(path, arcname)
                    accumulated += entry_size
                    count += 1
                except Exception as exc:
                    logger.warning("entry omitted from the download zip: %s", exc)
                    continue
    except Exception:
        buf.close()
        raise

    if count == 0:
        buf.close()
        return None, 0
    buf.seek(0)
    return buf, count


def build_batch_zip_bytes(con, file_ids: list[int]) -> tuple[bytes, int]:
    """Build ZIP bytes for callers that still need an in-memory payload."""
    buf, count = open_batch_zip_stream(con, file_ids)
    if buf is None:
        return b"", 0
    try:
        return buf.read(), count
    finally:
        buf.close()
