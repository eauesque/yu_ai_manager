"""PNG metadata extraction from in-memory bytes."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.extractors.png_bytes_chunks import parse_png_text_chunks
from core.extractors.png_bytes_match import match_png_chunks
from core.extractors.png_chunks import extract_png_text_chunks


def _empty_result() -> dict[str, Any]:
    return {
        "meta_source": None,
        "format": None,
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": None,
        "success": False,
    }


def extract_png_metadata_from_bytes(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _empty_result()

    try:
        chunks = parse_png_text_chunks(data)
    except Exception as e:
        logger.warning(f"PNG chunk parsing error: {e}")
        chunks = {}

    return match_png_chunks(chunks)


def extract_png_metadata(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return _empty_result()
    except Exception:
        return _empty_result()

    return match_png_chunks(extract_png_text_chunks(path))
