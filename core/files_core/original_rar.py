"""RAR-backed original media serving."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.infra_core.debug_log import dlog

from .media import (
    HEIF_AVAILABLE,
    guess_media_mime,
    is_browser_native_image,
    is_heif_file,
    is_media_file,
)
from .media_zip import zip_error_text
from .original_common import (
    bytes_or_cached_path,
    cached_path_response,
    convert_image_bytes_to_jpeg_response,
    guess_image_mime_from_suffix,
)
from .response_types import FileError, FileResult


def serve_rar_original(file_id: int, file_path_str: str) -> FileResult:
    import rarfile

    from core.helpers_core.helpers_text_path import split_archive_path
    from core.rar_core.rar_support_core import _resolve_entry_name
    archive_path_str, inner_path = split_archive_path(file_path_str)
    archive_path = Path(archive_path_str)
    if not archive_path.exists():
        dlog("files", "original.rar_not_found", file_id=file_id, archive_path=str(archive_path), entry=inner_path)
        return FileError(
            zip_error_text(
                "RARファイルが見つかりません",
                zip_path=archive_path,
                internal_path=inner_path,
                hint="元RARが移動/削除されていないか確認してください",
            ), 404)

    try:
        with rarfile.RarFile(archive_path_str, "r") as rf:
            target = _resolve_entry_name(rf.namelist(), inner_path)

        mime_type = guess_image_mime_from_suffix(target, guess_media_mime) or "application/octet-stream"

        if is_media_file(target):
            from .media_extract_cache import get_cached_path, store_fileobj_to_cache

            cached = get_cached_path(archive_path_str, inner_path)
            if cached is None:
                with rarfile.RarFile(archive_path_str, "r") as rf, rf.open(target) as src:
                    cached = store_fileobj_to_cache(archive_path_str, inner_path, src)
            return cached_path_response(cached, mime_type)

        with rarfile.RarFile(archive_path_str, "r") as rf, rf.open(target) as src:
            img_data = src.read()

        if (not is_browser_native_image(target)) and (not is_media_file(target)):
            if is_heif_file(target) and not HEIF_AVAILABLE:
                return FileError("HEIF/HEIC表示には pillow-heif が必要です (pip install pillow-heif)", 415)
            try:
                return convert_image_bytes_to_jpeg_response(img_data)
            except Exception as e:
                dlog("files", "original.rar_decode_error", file_id=file_id, detail=str(e))
                return FileError("画像の読み込みに失敗しました (形式不正または未対応)", 422)

        return bytes_or_cached_path(img_data, mime_type, archive_path_str, inner_path)
    except ImportError:
        return FileError("RAR対応には rarfile が必要です (pip install rarfile)", 500)
    except Exception as e:
        logger.error(f"RAR original error: {e}")
        dlog("files", "original.rar_error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        if isinstance(e, (KeyError, FileNotFoundError)):
            return FileError(
                zip_error_text(
                    "RAR内ファイルが見つかりません",
                    zip_path=archive_path,
                    internal_path=inner_path,
                    hint="再スキャンでRAR内エントリを更新してください",
                ), 404)
        if isinstance(e, (OSError, ValueError)):
            return FileError(
                zip_error_text(
                    "RAR原寸画像の読み込みに失敗しました",
                    zip_path=archive_path,
                    internal_path=inner_path,
                    hint="RAR破損や読み取り競合の可能性があります",
                ), 422)
        return FileError(
            zip_error_text(
                "RAR原寸画像の読み込みでエラーが発生しました",
                zip_path=archive_path,
                internal_path=inner_path,
                hint="再スキャン後も再現する場合はRARの整合性を確認してください",
            ), 500)
