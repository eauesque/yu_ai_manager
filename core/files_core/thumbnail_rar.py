"""RAR-backed thumbnail generation."""

import io
import logging
import tempfile
from pathlib import Path
from shutil import copyfileobj

logger = logging.getLogger(__name__)

from core.infra_core.debug_log import dlog
from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE

from .media import (
    HEIF_AVAILABLE,
    check_ffmpeg,
    corrupt_file_placeholder,
    extract_video_frame,
    heif_placeholder,
    is_audio_file,
    is_heif_file,
    is_video_file,
    jxl_placeholder,
    send_cached_image,
    unsupported_image_placeholder,
)
from .media_zip import zip_error_text
from .response_types import FileError, FileResult
from .thumbnail_common import save_image_thumbnail, vips_thumbnail_from_buffer


def serve_rar_thumbnail(file_id: int, file_path_str: str, cache_path: Path, image_module, image_error) -> FileResult:
    import rarfile

    from core.helpers_core.helpers_text_path import split_archive_path
    from core.rar_core.rar_support_core import _resolve_entry_name
    archive_path_str, inner_path = split_archive_path(file_path_str)
    archive_path = Path(archive_path_str)

    if not archive_path.exists():
        dlog("files", "thumbnail.rar_not_found", file_id=file_id, archive_path=str(archive_path), entry=inner_path)
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
            if rf.getinfo(target).file_size > ARCHIVE_MAX_ENTRY_SIZE:
                raise ValueError(f"Entry too large: {target}")
            if is_video_file(target):
                return _handle_rar_video_stream(rf, archive_path, target, cache_path)
            with rf.open(target) as src:
                img_data = src.read()
    except ImportError:
        return FileError("RAR対応には rarfile が必要です (pip install rarfile)", 500)
    except Exception as e:
        logger.error(f"RAR read error: {e}")
        dlog("files", "thumbnail.rar_error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        return corrupt_file_placeholder(cache_path, "RAR read error")

    if is_audio_file(target):
        import rarfile

        from core.rar_core.rar_support_core import _resolve_entry_name

        from .media import audio_placeholder, extract_album_art

        with rarfile.RarFile(archive_path_str, "r") as rf:
            resolved = _resolve_entry_name(rf.namelist(), target)
            with rf.open(resolved) as src:
                art = extract_album_art(src)
        if art:
            img = image_module.open(io.BytesIO(art))
            save_image_thumbnail(img, cache_path, image_module)
            return send_cached_image(cache_path)
        return audio_placeholder(cache_path, Path(target).name)

    return _handle_rar_image(img_data, target, cache_path, image_module, image_error)


def _handle_rar_video_stream(rf, archive_path: Path, target: str, cache_path: Path) -> FileResult:
    if not check_ffmpeg():
        return FileError(
            zip_error_text(
                "動画サムネイル生成に ffmpeg が必要です",
                zip_path=archive_path,
                internal_path=target,
                hint="docs/en/installation/ffmpeg.md を参照してください",
            ), 500)

    with tempfile.NamedTemporaryFile(suffix=Path(target).suffix, delete=False) as tmp_video:
        tmp_video_path = tmp_video.name
        with rf.open(target) as src:
            copyfileobj(src, tmp_video, length=1024 * 1024)
    try:
        if extract_video_frame(tmp_video_path, cache_path):
            return send_cached_image(cache_path)
        return corrupt_file_placeholder(cache_path, "video frame extraction failed")
    finally:
        Path(tmp_video_path).unlink(missing_ok=True)


def _handle_rar_image(data: bytes, target: str, cache_path: Path, image_module, image_error) -> FileResult:
    if is_heif_file(target) and not HEIF_AVAILABLE:
        return heif_placeholder(cache_path)

    if vips_thumbnail_from_buffer(data, cache_path):
        return send_cached_image(cache_path)

    try:
        img = image_module.open(io.BytesIO(data))
    except image_error:
        ext = Path(target).suffix.lower()
        if ext == ".jxl":
            return jxl_placeholder(cache_path)
        return unsupported_image_placeholder(cache_path, ext)

    save_image_thumbnail(img, cache_path, image_module)
    return send_cached_image(cache_path)
