"""ZIP-backed original media serving."""

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.infra_core.debug_log import dlog
from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE

from .media import (
    HEIF_AVAILABLE,
    guess_media_mime,
    is_browser_native_image,
    is_heif_file,
    is_media_file,
    resolve_zip_target,
    zip_error_text,
)
from .original_common import (
    bytes_or_cached_path,
    cached_path_response,
    convert_image_bytes_to_jpeg_response,
    guess_image_mime_from_suffix,
)
from .response_types import FileError, FileResult


def serve_zip_original(file_id: int, file_path_str: str) -> FileResult:
    import zipfile

    from core.helpers_core.helpers_text_path import split_archive_path
    zip_path_str, inner_path = split_archive_path(file_path_str)
    zip_path = Path(zip_path_str)
    if not zip_path.exists():
        dlog("files", "original.zip_not_found", file_id=file_id, zip_path=str(zip_path), entry=inner_path)
        return FileError(
            zip_error_text(
                "ZIPファイルが見つかりません",
                zip_path=zip_path,
                internal_path=inner_path,
                hint="元ZIPが移動/削除されていないか確認してください",
            ), 404)

    try:
        # Nested ZIP detection: inner_path is in "inner.zip!file.jpg" format
        _is_nested = "!" in inner_path and inner_path.split("!", 1)[0].lower().endswith(".zip")

        if _is_nested:
            nested_zip_name, nested_file = inner_path.split("!", 1)
            from core.zip_core.zip_read_single import _read_zip_entry_checked
            with zipfile.ZipFile(zip_path, "r") as outer_zf, zipfile.ZipFile(
                io.BytesIO(_read_zip_entry_checked(outer_zf, nested_zip_name, ARCHIVE_MAX_ENTRY_SIZE)),
                "r",
            ) as inner_zf:
                target = resolve_zip_target(inner_zf.namelist(), nested_file)
                if not target:
                    return FileError(
                        zip_error_text(
                            "ネストZIP内に対象ファイルが見つかりません",
                            zip_path=zip_path,
                            internal_path=inner_path,
                            hint="再スキャンでZIP内エントリを更新してください",
                        ), 404)
            mime_type = guess_image_mime_from_suffix(target, guess_media_mime) or "application/octet-stream"

            if is_media_file(target):
                from .media_extract_cache import get_cached_path, store_fileobj_to_cache

                cached = get_cached_path(zip_path_str, inner_path)
                if cached is None:
                    with zipfile.ZipFile(zip_path, "r") as outer_zf, zipfile.ZipFile(
                        io.BytesIO(_read_zip_entry_checked(outer_zf, nested_zip_name, ARCHIVE_MAX_ENTRY_SIZE)),
                        "r",
                    ) as inner_zf, inner_zf.open(target) as src:
                        cached = store_fileobj_to_cache(zip_path_str, inner_path, src)
                return cached_path_response(cached, mime_type)

            with zipfile.ZipFile(zip_path, "r") as outer_zf, zipfile.ZipFile(
                io.BytesIO(_read_zip_entry_checked(outer_zf, nested_zip_name, ARCHIVE_MAX_ENTRY_SIZE)),
                "r",
            ) as inner_zf, inner_zf.open(target) as f:
                img_data = f.read()

            if (not is_browser_native_image(target)) and (not is_media_file(target)):
                if is_heif_file(target) and not HEIF_AVAILABLE:
                    return FileError("HEIF/HEIC表示には pillow-heif が必要です（pip install pillow-heif）", 415)
                try:
                    return convert_image_bytes_to_jpeg_response(img_data)
                except Exception as e:
                    dlog("files", "original.zip_decode_error", file_id=file_id, detail=str(e))
                    return FileError("画像の読み込みに失敗しました（形式不正または未対応）", 422)

            return bytes_or_cached_path(img_data, mime_type, zip_path_str, inner_path)
        else:
            with zipfile.ZipFile(zip_path, "r") as zf:
                target = resolve_zip_target(zf.namelist(), inner_path)
                if not target:
                    return FileError(
                        zip_error_text(
                            "ZIP内に対象ファイルが見つかりません",
                            zip_path=zip_path,
                            internal_path=inner_path,
                            hint="再スキャンでZIP内エントリを更新してください",
                        ), 404)
            mime_type = guess_image_mime_from_suffix(target, guess_media_mime) or "application/octet-stream"

            if is_media_file(target):
                from .media_extract_cache import get_cached_path, store_fileobj_to_cache

                cached = get_cached_path(zip_path_str, inner_path)
                if cached is None:
                    with zipfile.ZipFile(zip_path, "r") as zf, zf.open(target) as src:
                        cached = store_fileobj_to_cache(zip_path_str, inner_path, src)
                return cached_path_response(cached, mime_type)

            with zipfile.ZipFile(zip_path, "r") as zf, zf.open(target) as f:
                img_data = f.read()

            if (not is_browser_native_image(target)) and (not is_media_file(target)):
                if is_heif_file(target) and not HEIF_AVAILABLE:
                    return FileError("HEIF/HEIC表示には pillow-heif が必要です（pip install pillow-heif）", 415)
                try:
                    return convert_image_bytes_to_jpeg_response(img_data)
                except Exception as e:
                    dlog("files", "original.zip_decode_error", file_id=file_id, detail=str(e))
                    return FileError("画像の読み込みに失敗しました（形式不正または未対応）", 422)

            return bytes_or_cached_path(img_data, mime_type, zip_path_str, inner_path)
    except zipfile.BadZipFile:
        dlog("files", "original.bad_zip", file_id=file_id, zip_path=str(zip_path))
        return FileError(
            zip_error_text(
                "ZIPファイルが破損しているため読み込めません",
                zip_path=zip_path,
                internal_path=inner_path,
                hint="ZIPを再作成するか元ファイルを再取得してください",
            ), 422)
    except Exception as e:
        logger.error(f"ZIP original error: {e}")
        dlog("files", "original.zip_error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        if isinstance(e, FileNotFoundError):
            return FileError(
                zip_error_text(
                    "ZIP内ファイルが見つかりません",
                    zip_path=zip_path,
                    internal_path=inner_path,
                    hint="再スキャンでZIP内エントリを更新してください",
                ), 404)
        if isinstance(e, (OSError, ValueError)):
            return FileError(
                zip_error_text(
                    "ZIP原寸画像の読み込みに失敗しました",
                    zip_path=zip_path,
                    internal_path=inner_path,
                    hint="ZIP破損や読み取り競合の可能性があります",
                ), 422)
        return FileError(
            zip_error_text(
                "ZIP原寸画像の読み込みでエラーが発生しました",
                zip_path=zip_path,
                internal_path=inner_path,
                hint="再スキャン後も再現する場合はZIPの整合性を確認してください",
            ), 500)
