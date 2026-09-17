"""Audio/Video metadata extraction (tinytag backend)."""

import io
from pathlib import Path
from typing import Any

from core.extractors.media_ffprobe import extract_with_ffprobe
from core.extractors.media_mutagen import extract_with_mutagen


def extract_media_metadata(path: Path) -> dict[str, Any]:
    """Extract media metadata from regular file path."""
    ffprobe_result = extract_with_ffprobe(path)
    if ffprobe_result.get("success"):
        return ffprobe_result
    return extract_with_mutagen(path)


def extract_media_metadata_from_bytes(data: bytes) -> dict[str, Any]:
    """Extract media metadata from bytes (e.g. ZIP member)."""
    bio = io.BytesIO(data)
    return extract_with_mutagen(bio)
