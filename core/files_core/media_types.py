"""Media type detection helpers."""

import os
from pathlib import Path

HEIF_AVAILABLE = False
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    pass

JXL_AVAILABLE = False
try:
    import pillow_jxl  # noqa: F401

    JXL_AVAILABLE = True
except ImportError:
    pass

PDF_AVAILABLE = False
try:
    from pdf2image import convert_from_path  # noqa: F401

    PDF_AVAILABLE = True
except ImportError:
    pass

SVG_AVAILABLE = False
try:
    from resvg import usvg as _usvg_check  # noqa: F401

    SVG_AVAILABLE = True
except ImportError:
    pass


_MEDIA_MIMES = {
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".ogv": "video/ogg",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


def is_heif_file(path_str: str) -> bool:
    ext = os.path.splitext(path_str)[1].lower()
    return ext in (".heif", ".heic")


def is_jxl_file(path_str: str) -> bool:
    return os.path.splitext(path_str)[1].lower() == ".jxl"


def is_svg_file(path_str: str) -> bool:
    return os.path.splitext(path_str)[1].lower() == ".svg"


def is_browser_native_image(path_str: str) -> bool:
    ext = os.path.splitext(path_str)[1].lower()
    return ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg"}


def guess_media_mime(path_str: str) -> str | None:
    ext = os.path.splitext(path_str)[1].lower()
    return _MEDIA_MIMES.get(ext)


def is_media_file(path_str: str) -> bool:
    return guess_media_mime(path_str) is not None


def is_video_file(path_str: str) -> bool:
    ext = Path(path_str).suffix.lower()
    return ext in [".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv"]


def is_audio_file(path_str: str) -> bool:
    ext = Path(path_str).suffix.lower()
    return ext in [".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac"]


def is_pdf_file(path_str: str) -> bool:
    return os.path.splitext(path_str)[1].lower() == ".pdf"


# Extensions that WD-Tagger (and similar image-analysis tools) can process.
_TAGGABLE_IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp", ".tiff", ".tif",
}

# Add optional formats when their decoders are available.
if HEIF_AVAILABLE:
    _TAGGABLE_IMAGE_EXTS |= {".heif", ".heic"}
if JXL_AVAILABLE:
    _TAGGABLE_IMAGE_EXTS.add(".jxl")
if SVG_AVAILABLE:
    _TAGGABLE_IMAGE_EXTS.add(".svg")

# Video extensions handled via keyframe extraction.
_TAGGABLE_VIDEO_EXTS = {".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv"}


def is_taggable_file(path_str: str) -> bool:
    """Return True if the file is an image or video that analysis tools can process.

    Excludes audio (.wav, .mp3 ...), PDFs, and other non-visual formats.
    """
    ext = os.path.splitext(path_str)[1].lower()
    return ext in _TAGGABLE_IMAGE_EXTS or ext in _TAGGABLE_VIDEO_EXTS
