import logging

logger = logging.getLogger(__name__)

_MEDIA_EXTS = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif",
        ".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv",
    }
)


def is_processable_file(path: str) -> bool:
    import os

    if "!" in path:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in _MEDIA_EXTS and os.path.exists(path)


def mark_unprocessable_bulk(source: str) -> int:
    # mark_unprocessable_detection_files() already submits to the writer queue;
    # wrapping it again would re-submit from inside the writer thread.
    from core.services_core.yolo_detection_service import (
        mark_unprocessable_detection_files,
    )

    return mark_unprocessable_detection_files(source)


def group_by_archive(items: list) -> dict:
    from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path

    groups: dict = {}
    for fid, path in items:
        if is_archive_member(path):
            archive_path, _inner = split_archive_path(path)
            groups.setdefault(archive_path, []).append((fid, path))
        else:
            groups.setdefault("", []).append((fid, path))
    return groups
