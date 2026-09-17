"""Format-specific metadata extraction."""

from core.extractors.exif_chunks import (
    extract_exif_chunks,
    extract_exif_chunks_from_bytes,
)
from core.extractors.exif_jpeg import (
    extract_jpeg_metadata,
    extract_jpeg_metadata_from_bytes,
)
from core.extractors.media import extract_media_metadata, extract_media_metadata_from_bytes
from core.extractors.png_bytes import extract_png_metadata, extract_png_metadata_from_bytes
from core.extractors.png_chunks import extract_png_text_chunks
from core.extractors.sidecar import read_sidecar_txt
from core.extractors.webm import extract_webm_metadata
from core.extractors.webp_bytes import (
    extract_webp_metadata,
    extract_webp_metadata_from_bytes,
)
from core.extractors.webp_chunks import extract_webp_text_chunks
from core.extractors.webp_novelai import extract_novelai_webp_metadata

__all__ = [
    "extract_png_metadata",
    "extract_png_text_chunks", "extract_png_metadata_from_bytes",
    "extract_webp_metadata",
    "extract_webp_text_chunks", "extract_novelai_webp_metadata", "extract_webp_metadata_from_bytes",
    "extract_webm_metadata",
    "extract_jpeg_metadata",
    "extract_jpeg_metadata_from_bytes",
    "extract_exif_chunks", "extract_exif_chunks_from_bytes",
    "read_sidecar_txt",
    "extract_media_metadata", "extract_media_metadata_from_bytes",
]
