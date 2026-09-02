"""Metadata extraction helpers facade for regular scanner."""

from .scanner_regular_meta_chunks import extract_chunks_for_file
from .scanner_regular_meta_fallbacks import (
    apply_bytes_metadata_fallback,
    apply_chunk_fallback,
    apply_media_metadata_fallback,
)

__all__ = [
    "apply_bytes_metadata_fallback",
    "apply_chunk_fallback",
    "apply_media_metadata_fallback",
    "extract_chunks_for_file",
]
