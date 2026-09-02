"""Original file serving service used by routes/files.py."""

import logging

logger = logging.getLogger(__name__)
from core.infra_core.debug_log import dlog
from core.services_core.media_extract_state import queue_media_extract_access_touch

from .original_plain import serve_plain_original
from .original_rar import serve_rar_original
from .original_sevenz import serve_7z_original
from .original_zip import serve_zip_original
from .response_types import FileError, FileResult


def _is_7z_archive_path(path: str) -> bool:
    from core.helpers_core.helpers_text_path import archive_part
    return archive_part(path).lower().endswith(".7z")


def _is_rar_archive_path(path: str) -> bool:
    from core.helpers_core.helpers_text_path import archive_part
    return archive_part(path).lower().endswith(".rar")


def _deferred_touch_media(file_id: int) -> None:
    """Best-effort media access recording in the background."""
    try:
        queue_media_extract_access_touch(int(file_id))
    except Exception as exc:
        logger.debug("Deferred media touch skipped: %s", exc)


def _lookup_original_path(file_id: int):
    from .thumbnail_common import lookup_thumbnail_source
    source = lookup_thumbnail_source(file_id)
    if not source:
        return None
    _deferred_touch_media(int(file_id))
    return source[0]


def serve_original(file_id: int) -> FileResult:
    file_path_str = _lookup_original_path(file_id)
    if not file_path_str:
        dlog("files", "original.not_found", file_id=file_id)
        return FileError("Not found", 404)

    try:
        from core.helpers_core.helpers_text_path import is_archive_member

        is_archive = is_archive_member(file_path_str)
        dlog("files", "original.request", file_id=file_id, zip_mode=is_archive, path=file_path_str)
        if is_archive:
            if _is_7z_archive_path(file_path_str):
                return serve_7z_original(file_id, file_path_str)
            if _is_rar_archive_path(file_path_str):
                return serve_rar_original(file_id, file_path_str)
            return serve_zip_original(file_id, file_path_str)
        return serve_plain_original(file_id, file_path_str)
    except Exception as e:
        logger.error(f"Original image error: {e}", exc_info=True)
        dlog("files", "original.error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        return FileError("原寸画像の読み込みに失敗しました", 500)
