"""Compatibility facade for PNG extraction APIs.

External compatibility only. Repo-internal code should prefer
``png_bytes``, ``png_chunks``, and ``exif_user_comment`` directly.
"""

from core.extractors.exif_user_comment import _exif_read_u16, _exif_read_u32, _parse_exif_user_comment
from core.extractors.png_bytes import extract_png_metadata, extract_png_metadata_from_bytes
from core.extractors.png_chunks import extract_png_text_chunks

__all__ = [
    "_exif_read_u16",
    "_exif_read_u32",
    "_parse_exif_user_comment",
    "extract_png_text_chunks",
    "extract_png_metadata",
    "extract_png_metadata_from_bytes",
]
