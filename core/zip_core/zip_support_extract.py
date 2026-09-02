"""ZIP-internal metadata extraction helpers."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from core.helpers_core.archive_member_temp import extracted_zip_member_path

from .zip_support_core import read_bytes_from_zip
from .zip_support_extract_dispatch import apply_extractor_by_extension, is_media_metadata_extension


def _set_a1111_tag_source(result: dict[str, Any]) -> None:
    if not result.get("success") or not result.get("raw_prompt") or "tag_source" in result:
        return

    raw = result["raw_prompt"]
    if "Steps:" not in raw and "Negative prompt:" not in raw:
        return

    from core.prompt import parse_a1111_prompt

    parsed = parse_a1111_prompt(raw)
    result["tag_source"] = parsed.get("positive", raw)
    if not result.get("raw_negative") and parsed.get("negative"):
        result["raw_negative"] = parsed["negative"]


def extract_metadata_from_zip(zip_path: str, internal_path: str) -> dict[str, Any]:
    """Extract metadata from ZIP entry bytes."""
    result: dict[str, Any] = {
        "meta_source": None,
        "format": None,
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": None,
        "success": False,
    }

    try:
        if is_media_metadata_extension(internal_path):
            with extracted_zip_member_path(zip_path, internal_path) as extracted:
                apply_extractor_by_extension(result, internal_path, extracted)
        else:
            file_bytes = read_bytes_from_zip(zip_path, internal_path)
            apply_extractor_by_extension(result, internal_path, file_bytes)
    except Exception as e:
        logger.warning(f"Failed to extract metadata from ZIP: {zip_path}!{internal_path}: {e}")

    _set_a1111_tag_source(result)
    return result
