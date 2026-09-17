"""Common helpers for original file serving."""

import io
from pathlib import Path

from .response_types import FileBytes, FilePath, FileResult

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}


def convert_image_bytes_to_jpeg_response(img_data: bytes) -> FileBytes:
    from PIL import Image

    with Image.open(io.BytesIO(img_data)) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=95)
    return FileBytes(data=buf.getvalue(), mime_type="image/jpeg")


def convert_image_path_to_jpeg_response(file_path: Path) -> FileBytes:
    from PIL import Image

    with Image.open(file_path) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=95)
    return FileBytes(data=buf.getvalue(), mime_type="image/jpeg")


def guess_image_mime_from_suffix(path_or_name: str, fallback_guess):
    ext = Path(path_or_name).suffix.lower()
    return _IMAGE_MIME_TYPES.get(ext) or fallback_guess(path_or_name)


def build_etag_from_stat(file_stat):
    return f'"{file_stat.st_size:x}-{int(file_stat.st_mtime):x}"'


def cached_path_response(path: Path, mime_type: str) -> FilePath:
    """Wrap a cached on-disk file as a FilePath response."""
    return FilePath(
        path=path,
        mime_type=mime_type,
        etag=build_etag_from_stat(path.stat()),
    )


def bytes_or_cached_path(
    data: bytes, mime_type: str, archive_path: str, inner_path: str,
) -> FileResult:
    """Return extracted video/audio from archives via cached FilePath.

    For non-video/non-audio files, returns FileBytes as before.
    """
    from .media_extract_cache import get_cached_path, is_streamable_media, store_to_cache

    if not is_streamable_media(inner_path):
        return FileBytes(data=data, mime_type=mime_type)

    # Check cache hit
    cached = get_cached_path(archive_path, inner_path)
    if cached is None:
        cached = store_to_cache(archive_path, inner_path, data)

    etag = build_etag_from_stat(cached.stat())
    return FilePath(path=cached, mime_type=mime_type, etag=etag)
