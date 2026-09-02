"""Shared media helpers for file routes (compat facade)."""

from .media_album_art import extract_album_art
from .media_placeholders import (
    audio_placeholder,
    corrupt_file_placeholder,
    heif_placeholder,
    jxl_placeholder,
    pdf_placeholder,
    send_cached_image,
    svg_placeholder,
    unsupported_image_placeholder,
)
from .media_types import (
    HEIF_AVAILABLE,
    JXL_AVAILABLE,
    PDF_AVAILABLE,
    SVG_AVAILABLE,
    guess_media_mime,
    is_audio_file,
    is_browser_native_image,
    is_heif_file,
    is_jxl_file,
    is_media_file,
    is_pdf_file,
    is_svg_file,
    is_video_file,
)
from .media_video import check_ffmpeg, extract_video_frame
from .media_zip import resolve_zip_target, zip_error_text
from .video_keyframes import extract_keyframes, video_keyframes_context
from .video_tag_merge import merge_wd_tag_results

__all__ = [
    "HEIF_AVAILABLE",
    "JXL_AVAILABLE",
    "PDF_AVAILABLE",
    "SVG_AVAILABLE",
    "is_heif_file",
    "is_jxl_file",
    "is_pdf_file",
    "is_svg_file",
    "is_browser_native_image",
    "guess_media_mime",
    "is_media_file",
    "is_video_file",
    "is_audio_file",
    "check_ffmpeg",
    "extract_video_frame",
    "heif_placeholder",
    "jxl_placeholder",
    "pdf_placeholder",
    "svg_placeholder",
    "unsupported_image_placeholder",
    "audio_placeholder",
    "corrupt_file_placeholder",
    "send_cached_image",
    "extract_album_art",
    "resolve_zip_target",
    "zip_error_text",
    "extract_keyframes",
    "video_keyframes_context",
    "merge_wd_tag_results",
]
