"""7z-backed thumbnail generation."""

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


def serve_7z_thumbnail(file_id: int, file_path_str: str, cache_path: Path, image_module, image_error) -> FileResult:
    from core.helpers_core.helpers_text_path import split_archive_path
    from core.sevenz_core import sevenz_cli
    from core.sevenz_core.sevenz_support_core import _resolve_entry_name
    archive_path_str, inner_path = split_archive_path(file_path_str)
    archive_path = Path(archive_path_str)

    if not archive_path.exists():
        dlog("files", "thumbnail.7z_not_found", file_id=file_id, archive_path=str(archive_path), entry=inner_path)
        return FileError(
            zip_error_text(
                "7zファイルが見つかりません",
                zip_path=archive_path,
                internal_path=inner_path,
                hint="元7zが移動/削除されていないか確認してください",
            ), 404)

    try:
        target = _resolve_entry_name(sevenz_cli.list_names(archive_path_str), inner_path)
        if is_video_file(target):
            return _handle_7z_video_path(archive_path_str, archive_path, target, cache_path)

        img_data = sevenz_cli.read_entry_bytes(archive_path_str, target, max_size=ARCHIVE_MAX_ENTRY_SIZE)
    except ImportError:
        return FileError("7z対応には 7z CLI が必要です（7-Zip をインストールしてください）", 500)
    except Exception as e:
        logger.error(f"7z read error: {e}")
        dlog("files", "thumbnail.7z_error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        return corrupt_file_placeholder(cache_path, "7z read error")

    if is_audio_file(target):
        from core.helpers_core.archive_member_temp import extracted_7z_member_path

        from .media import audio_placeholder, extract_album_art

        with extracted_7z_member_path(archive_path_str, target) as extracted:
            art = extract_album_art(extracted)
        if art:
            img = image_module.open(io.BytesIO(art))
            save_image_thumbnail(img, cache_path, image_module)
            return send_cached_image(cache_path)
        return audio_placeholder(cache_path, Path(target).name)

    return _handle_7z_image(img_data, target, cache_path, image_module, image_error)


def _handle_7z_video_path(archive_path_str: str, archive_path: Path, target: str, cache_path: Path) -> FileResult:
    from core.sevenz_core import sevenz_cli

    if not check_ffmpeg():
        return FileError(
            zip_error_text(
                "動画サムネイル生成に ffmpeg が必要です",
                zip_path=archive_path,
                internal_path=target,
                hint="docs/en/installation/ffmpeg.md を参照してください",
            ), 500)

    with tempfile.TemporaryDirectory() as tmpdir:
        sevenz_cli.extract_to_dir(archive_path_str, tmpdir, targets=[target], max_size=ARCHIVE_MAX_ENTRY_SIZE)
        extracted = Path(tmpdir, *target.split("/"))
        if not extracted.exists():
            return corrupt_file_placeholder(cache_path, "7z extract failed")
        suffix = extracted.suffix or Path(target).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_video:
            tmp_video_path = tmp_video.name
            with extracted.open("rb") as src:
                copyfileobj(src, tmp_video, length=1024 * 1024)
    try:
        if extract_video_frame(tmp_video_path, cache_path):
            return send_cached_image(cache_path)
        return corrupt_file_placeholder(cache_path, "video frame extraction failed")
    finally:
        Path(tmp_video_path).unlink(missing_ok=True)


def _handle_7z_image(data: bytes, target: str, cache_path: Path, image_module, image_error) -> FileResult:
    if is_heif_file(target) and not HEIF_AVAILABLE:
        return heif_placeholder(cache_path)

    # pyvips fast path (generate thumbnail from buffer)
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
