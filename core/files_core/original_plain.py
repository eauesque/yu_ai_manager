"""Filesystem-backed original media serving."""

from pathlib import Path

from core.infra_core.debug_log import dlog

from .media import (
    HEIF_AVAILABLE,
    JXL_AVAILABLE,
    guess_media_mime,
    is_browser_native_image,
    is_heif_file,
    is_jxl_file,
    is_media_file,
    is_pdf_file,
    is_svg_file,
)
from .original_common import (
    build_etag_from_stat,
    convert_image_path_to_jpeg_response,
    guess_image_mime_from_suffix,
)
from .plain_faststart_cache import get_faststarted_path
from .response_types import FileError, FilePath, FileResult


def _convert_or_error(file_path: Path, file_id: int, log_key: str) -> FileResult:
    try:
        return convert_image_path_to_jpeg_response(file_path)
    except FileNotFoundError:
        return FileError("ファイルが見つかりません", 404)
    except OSError as e:
        dlog("files", log_key, file_id=file_id, detail=str(e))
        return FileError("画像の読み込みに失敗しました（形式不正または破損）", 422)


def serve_plain_original(file_id: int, file_path_str: str) -> FileResult:
    file_path = Path(file_path_str)
    if not file_path.exists():
        return FileError("ファイルが見つかりません", 404)

    # SVG: serve directly with sandbox CSP to prevent embedded JS execution
    if is_svg_file(file_path_str):
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return FileError("ファイルが見つかりません", 404)
        etag = build_etag_from_stat(stat)
        return FilePath(
            path=file_path,
            mime_type="image/svg+xml",
            etag=etag,
            extra_headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                "X-Content-Type-Options": "nosniff",
            },
        )

    # PDF: serve directly with application/pdf (browser or OS handles display)
    if is_pdf_file(file_path_str):
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return FileError("ファイルが見つかりません", 404)
        etag = build_etag_from_stat(stat)
        return FilePath(path=file_path, mime_type="application/pdf", etag=etag)

    if (not is_browser_native_image(file_path_str)) and (not is_media_file(file_path_str)):
        if is_heif_file(file_path_str) and not HEIF_AVAILABLE:
            return FileError("HEIF/HEIC表示には pillow-heif が必要です（pip install pillow-heif）", 415)
        if is_jxl_file(file_path_str) and not JXL_AVAILABLE:
            return FileError("JPEG XL (.jxl) 表示には pillow-jxl-plugin が必要です（pip install pillow-jxl-plugin）", 415)
        return _convert_or_error(file_path, file_id, "original.decode_error")

    if is_heif_file(file_path_str):
        if HEIF_AVAILABLE:
            return _convert_or_error(file_path, file_id, "original.heif_decode_error")
        return FileError("HEIF/HEIC表示には pillow-heif が必要です（pip install pillow-heif）", 415)

    mime_type = guess_image_mime_from_suffix(file_path_str, guess_media_mime)

    try:
        stat = file_path.stat()
    except FileNotFoundError:
        return FileError("ファイルが見つかりません", 404)

    etag = build_etag_from_stat(stat)

    try:
        # Verify file is readable
        with file_path.open("rb"):
            pass
    except FileNotFoundError:
        return FileError("ファイルが見つかりません", 404)
    except OSError as e:
        dlog("files", "original.send_file_error", file_id=file_id, detail=str(e))
        return FileError("画像ファイルの読み込みに失敗しました", 422)

    # MP4/MOV: serve faststarted cache if moov atom is at the end
    # This allows the browser to start progressive playback from the beginning
    faststarted = get_faststarted_path(file_path)
    if faststarted is not None:
        fs_etag = build_etag_from_stat(faststarted.stat())
        return FilePath(path=faststarted, mime_type=mime_type, etag=fs_etag)

    return FilePath(path=file_path, mime_type=mime_type, etag=etag)
