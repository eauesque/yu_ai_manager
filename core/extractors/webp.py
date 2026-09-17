"""Compatibility facade for WebP metadata extraction.

External compatibility only. Repo-internal code should prefer
``webp_bytes``, ``webp_chunks``, and ``webp_novelai`` directly.
"""

from core.extractors.webp_bytes import extract_webp_metadata, extract_webp_metadata_from_bytes
from core.extractors.webp_chunks import extract_webp_text_chunks
from core.extractors.webp_novelai import extract_novelai_webp_metadata

__all__ = [
    "extract_webp_text_chunks",
    "extract_novelai_webp_metadata",
    "extract_webp_metadata",
    "extract_webp_metadata_from_bytes",
]
