"""JPEG metadata extraction helpers using EXIF comment parser."""

from pathlib import Path
from typing import Any

from core.extractors.exif_comment_decode import extract_exif_user_comment, extract_exif_user_comment_from_bytes


def _empty_result() -> dict[str, Any]:
    return {
        "meta_source": None,
        "format": None,
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": None,
        "success": False,
    }


def _build_result_from_text(text: str | None) -> dict[str, Any]:
    result = _empty_result()
    if text and ("Steps:" in text or "Sampler:" in text):
        result["raw_prompt"] = text
        result["meta_source"] = "a1111_jpg"
        result["format"] = "sd"
        result["success"] = True
    return result


def extract_jpeg_metadata_from_bytes(data: bytes) -> dict[str, Any]:
    result = _empty_result()
    if not data or data[:2] != b"\xff\xd8":
        return result

    return _build_result_from_text(extract_exif_user_comment_from_bytes(data))


def extract_jpeg_metadata(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            if f.read(2) != b"\xff\xd8":
                return _empty_result()
    except Exception:
        return _empty_result()
    return _build_result_from_text(extract_exif_user_comment(path))
