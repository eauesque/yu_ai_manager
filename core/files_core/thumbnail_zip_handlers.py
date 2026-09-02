"""Helper handlers for ZIP thumbnail generation."""

import io
import tempfile
from pathlib import Path
from shutil import copyfileobj

from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE
from core.zip_core.zip_read_single import _ensure_zip_entry_safe

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
    zip_error_text,
)
from .response_types import FileError, FileResult
from .thumbnail_common import save_image_thumbnail, vips_thumbnail_from_buffer


def handle_zip_video(zf, zip_path: Path, target: str, cache_path: Path) -> FileResult:
    _ensure_zip_entry_safe(zf.getinfo(target), target, ARCHIVE_MAX_ENTRY_SIZE)
    if not check_ffmpeg():
        return FileError(
            zip_error_text(
                "動画サムネイル生成に ffmpeg が必要です",
                zip_path=zip_path,
                internal_path=target,
                hint="docs/en/installation/ffmpeg.md を参照してください",
            ), 500)

    with tempfile.NamedTemporaryFile(suffix=Path(target).suffix, delete=False) as tmp_video:
        tmp_video_path = tmp_video.name
        with zf.open(target) as src:
            copyfileobj(src, tmp_video, length=1024 * 1024)
    try:
        if extract_video_frame(tmp_video_path, cache_path):
            return send_cached_image(cache_path)
        return corrupt_file_placeholder(cache_path, "video frame extraction failed")
    finally:
        Path(tmp_video_path).unlink(missing_ok=True)


def handle_zip_image(zf, target: str, cache_path: Path, image_module, image_error) -> FileResult:
    _ensure_zip_entry_safe(zf.getinfo(target), target, ARCHIVE_MAX_ENTRY_SIZE)
    with zf.open(target) as f:
        data = f.read(ARCHIVE_MAX_ENTRY_SIZE + 1)
    if len(data) > ARCHIVE_MAX_ENTRY_SIZE:
        raise ValueError(f"Entry too large: {target}")

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


def handle_zip_target(zf, zip_path: Path, target: str, cache_path: Path, image_module, image_error) -> FileResult:
    _ensure_zip_entry_safe(zf.getinfo(target), target, ARCHIVE_MAX_ENTRY_SIZE)
    if is_audio_file(target):
        from .media import audio_placeholder, extract_album_art
        with zf.open(target) as f:
            art = extract_album_art(f)
        if art:
            img = image_module.open(io.BytesIO(art))
            save_image_thumbnail(img, cache_path, image_module)
            return send_cached_image(cache_path)
        return audio_placeholder(cache_path, Path(target).name)

    if is_video_file(target):
        return handle_zip_video(zf, zip_path, target, cache_path)

    return handle_zip_image(zf, target, cache_path, image_module, image_error)
