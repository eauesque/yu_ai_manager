"""7z-backed original media serving."""

import logging
import tempfile
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


def serve_7z_original(file_id: int, file_path_str: str) -> FileResult:
    from core.helpers_core.helpers_text_path import split_archive_path
    from core.sevenz_core import sevenz_cli
    from core.sevenz_core.sevenz_support_core import _resolve_entry_name
    archive_path_str, inner_path = split_archive_path(file_path_str)
    archive_path = Path(archive_path_str)
    if not archive_path.exists():
        dlog("files", "original.7z_not_found", file_id=file_id, archive_path=str(archive_path), entry=inner_path)
        return FileError(
            zip_error_text(
                "7zファイルが見つかりません",
                zip_path=archive_path,
                internal_path=inner_path,
                hint="元7zが移動/削除されていないか確認してください",
            ), 404)

    try:
        names = sevenz_cli.list_names(archive_path_str)
        target = _resolve_entry_name(names, inner_path)

        mime_type = guess_image_mime_from_suffix(target, guess_media_mime) or "application/octet-stream"

        if is_media_file(target):
            from .media_extract_cache import get_cached_path, store_fileobj_to_cache

            cached = get_cached_path(archive_path_str, inner_path)
            if cached is None:
                with tempfile.TemporaryDirectory() as tmpdir:
                    sevenz_cli.extract_to_dir(archive_path_str, tmpdir, targets=[target])
                    extracted = Path(tmpdir, *target.split("/"))
                    if not extracted.exists():
                        raise FileNotFoundError(target)
                    with extracted.open("rb") as src:
                        cached = store_fileobj_to_cache(archive_path_str, inner_path, src)
            return cached_path_response(cached, mime_type)

        img_data = sevenz_cli.read_entry_bytes(archive_path_str, target)

        if (not is_browser_native_image(target)) and (not is_media_file(target)):
            if is_heif_file(target) and not HEIF_AVAILABLE:
                return FileError("HEIF/HEIC表示には pillow-heif が必要です（pip install pillow-heif）", 415)
            try:
                return convert_image_bytes_to_jpeg_response(img_data)
            except Exception as e:
                dlog("files", "original.7z_decode_error", file_id=file_id, detail=str(e))
                return FileError("画像の読み込みに失敗しました（形式不正または未対応）", 422)

        return bytes_or_cached_path(img_data, mime_type, archive_path_str, inner_path)
    except ImportError:
        return FileError("7z対応には 7z CLI が必要です（7-Zip をインストールしてください）", 500)
    except Exception as e:
        logger.error(f"7z original error: {e}")
        dlog("files", "original.7z_error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        if isinstance(e, (KeyError, FileNotFoundError)):
            return FileError(
                zip_error_text(
                    "7z内ファイルが見つかりません",
                    zip_path=archive_path,
                    internal_path=inner_path,
                    hint="再スキャンで7z内エントリを更新してください",
                ), 404)
        if isinstance(e, (OSError, ValueError)):
            return FileError(
                zip_error_text(
                    "7z原寸画像の読み込みに失敗しました",
                    zip_path=archive_path,
                    internal_path=inner_path,
                    hint="7z破損や読み取り競合の可能性があります",
                ), 422)
        return FileError(
            zip_error_text(
                "7z原寸画像の読み込みでエラーが発生しました",
                zip_path=archive_path,
                internal_path=inner_path,
                hint="再スキャン後も再現する場合は7zの整合性を確認してください",
            ), 500)
