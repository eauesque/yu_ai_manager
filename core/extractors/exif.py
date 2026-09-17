"""Compatibility facade for EXIF extraction APIs.

External compatibility only. Repo-internal code should prefer
``exif_chunks``, ``exif_comment_decode``, and ``exif_jpeg`` directly.
"""

from core.extractors.exif_chunks import extract_exif_chunks, extract_exif_chunks_from_bytes
from core.extractors.exif_comment_decode import (
    decode_exif_user_comment,
    extract_exif_user_comment,
    extract_exif_user_comment_from_bytes,
)
from core.extractors.exif_jpeg import extract_jpeg_metadata, extract_jpeg_metadata_from_bytes

__all__ = [
    "decode_exif_user_comment",
    "extract_exif_user_comment",
    "extract_exif_user_comment_from_bytes",
    "extract_exif_chunks",
    "extract_exif_chunks_from_bytes",
    "extract_jpeg_metadata",
    "extract_jpeg_metadata_from_bytes",
]
