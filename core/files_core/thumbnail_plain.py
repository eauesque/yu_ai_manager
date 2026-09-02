"""Filesystem-backed thumbnail generation."""

import io
from pathlib import Path

from .media import (
    HEIF_AVAILABLE,
    JXL_AVAILABLE,
    PDF_AVAILABLE,
    SVG_AVAILABLE,
    audio_placeholder,
    check_ffmpeg,
    corrupt_file_placeholder,
    extract_album_art,
    extract_video_frame,
    heif_placeholder,
    is_audio_file,
    is_heif_file,
    is_jxl_file,
    is_pdf_file,
    is_svg_file,
    is_video_file,
    jxl_placeholder,
    pdf_placeholder,
    send_cached_image,
    svg_placeholder,
    unsupported_image_placeholder,
)
from .response_types import FileError, FileResult
from .thumbnail_common import save_image_thumbnail, vips_thumbnail_from_path


def _generate_svg_thumbnail(file_path: Path, cache_path: Path, image_module) -> FileResult:
    """Rasterize an SVG file to a JPEG thumbnail."""
    try:
        from .svg_raster import rasterize_svg
    except ImportError:
        return svg_placeholder(cache_path)

    try:
        png_data = rasterize_svg(file_path, 800, 800, background="#ffffff")
        if not png_data:
            return svg_placeholder(cache_path)
        img = image_module.open(io.BytesIO(png_data))
        save_image_thumbnail(img, cache_path, image_module)
        return send_cached_image(cache_path)
    except Exception:
        return svg_placeholder(cache_path)


_PDF_PREVIEW_PAGE = 3  # 0-based → page 4


def _generate_pdf_thumbnail(file_path: Path, cache_path: Path, image_module) -> FileResult:
    """Render a PDF page to a JPEG thumbnail using pdf2image (poppler)."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return pdf_placeholder(cache_path)

    try:
        # _PDF_PREVIEW_PAGE is 0-based; pdf2image uses 1-based
        page_1based = _PDF_PREVIEW_PAGE + 1
        images = convert_from_path(
            str(file_path),
            dpi=144,
            first_page=page_1based,
            last_page=page_1based,
        )
        if not images:
            return pdf_placeholder(cache_path)
        save_image_thumbnail(images[0], cache_path, image_module)
        return send_cached_image(cache_path)
    except Exception:
        return pdf_placeholder(cache_path)


def serve_plain_thumbnail(file_path_str: str, cache_path: Path, image_module, image_error) -> FileResult:
    file_path = Path(file_path_str)
    if not file_path.exists():
        return FileError("ファイルが見つかりません", 404)

    if is_svg_file(file_path_str):
        if not SVG_AVAILABLE:
            return svg_placeholder(cache_path)
        return _generate_svg_thumbnail(file_path, cache_path, image_module)

    if is_pdf_file(file_path_str):
        if not PDF_AVAILABLE:
            return pdf_placeholder(cache_path)
        return _generate_pdf_thumbnail(file_path, cache_path, image_module)

    if is_audio_file(file_path_str):
        art = extract_album_art(file_path)
        if art:
            img = image_module.open(io.BytesIO(art))
            save_image_thumbnail(img, cache_path, image_module)
            return send_cached_image(cache_path)
        return audio_placeholder(cache_path, file_path.name)

    if is_video_file(file_path_str):
        if not check_ffmpeg():
            return FileError("動画サムネイル生成に ffmpeg が必要です（docs/en/installation/ffmpeg.md）", 500)
        if extract_video_frame(file_path, cache_path):
            return send_cached_image(cache_path)
        return corrupt_file_placeholder(cache_path, "video frame extraction failed")

    if is_heif_file(file_path_str) and not HEIF_AVAILABLE:
        return heif_placeholder(cache_path)

    if is_jxl_file(file_path_str):
        if not JXL_AVAILABLE:
            return jxl_placeholder(cache_path)
        # JXL: fast path if pyvips supports it
        if vips_thumbnail_from_path(file_path_str, cache_path):
            return send_cached_image(cache_path)
        try:
            img = image_module.open(file_path)
        except image_error:
            return jxl_placeholder(cache_path)
        save_image_thumbnail(img, cache_path, image_module)
        return send_cached_image(cache_path)

    # General images: pyvips fast path (shrink-on-load makes JPEG/PNG/WebP significantly faster)
    if vips_thumbnail_from_path(file_path_str, cache_path):
        return send_cached_image(cache_path)

    try:
        img = image_module.open(file_path)
    except image_error:
        return unsupported_image_placeholder(cache_path, file_path.suffix.lower())

    save_image_thumbnail(img, cache_path, image_module)
    return send_cached_image(cache_path)
