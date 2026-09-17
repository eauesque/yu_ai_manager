"""WebP metadata extraction from in-memory bytes."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _empty_result() -> dict[str, Any]:
    return {
        "meta_source": None,
        "format": None,
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": None,
        "success": False,
    }


def extract_webp_metadata_from_bytes(data: bytes) -> dict[str, Any]:
    result = _empty_result()
    if not data.startswith(b"RIFF") or b"WEBP" not in data[:12]:
        return result

    try:
        return _extract_webp_metadata(data, result)
    except ImportError:
        return result
    except Exception as e:
        logger.warning(f"WebP metadata extraction error: {e}")
        return result


def extract_webp_metadata(path: Path) -> dict[str, Any]:
    result = _empty_result()
    try:
        with path.open("rb") as f:
            if f.read(4) != b"RIFF":
                return result
            f.seek(8)
            if f.read(4) != b"WEBP":
                return result
    except Exception:
        return result

    try:
        return _extract_webp_metadata(path, result)
    except ImportError:
        return result
    except Exception as e:
        logger.warning(f"WebP metadata extraction error: {e}")
        return result


def _extract_webp_metadata(source: bytes | Path, result: dict[str, Any]) -> dict[str, Any]:
    import io

    from PIL import Image

    image_source = io.BytesIO(source) if isinstance(source, bytes) else str(source)

    with Image.open(image_source) as img:
        exif = img.getexif()

        user_comment = exif.get(0x9286) if exif else None
        if not user_comment:
            info = img.info or {}
            user_comment = _extract_user_comment_from_info(info)

    if isinstance(user_comment, bytes):
        user_comment = user_comment.decode("utf-8", errors="ignore")
    if not isinstance(user_comment, str):
        return result

    return _build_result_from_user_comment(user_comment, result)


def _extract_user_comment_from_info(info: dict[str, Any]) -> str:
    exif_bytes = info.get("exif")
    if not exif_bytes:
        return ""
    idx = exif_bytes.find(b"UNICODE\x00")
    if idx >= 0:
        # Delegate to BOM + marker heuristic so NovelAI (UTF-16-BE) and
        # yu_ai_manager bridge (UTF-16-LE) both round-trip correctly.
        from core.extractors.exif_decode import _decode_unicode_user_comment
        decoded = _decode_unicode_user_comment(exif_bytes[idx + 8:])
        return (decoded or "").strip("\x00")
    idx = exif_bytes.find(b"ASCII\x00\x00\x00")
    if idx >= 0:
        return exif_bytes[idx + 8:].decode("ascii", errors="ignore").strip("\x00")
    return ""


def _build_result_from_user_comment(user_comment: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        meta = json.loads(user_comment)
    except json.JSONDecodeError:
        return result
    if not isinstance(meta, dict):
        return result

    comment_str = meta.get("Comment", "")
    desc_str = meta.get("Description", "")

    is_v4 = False
    if comment_str:
        try:
            parsed = json.loads(comment_str)
            is_v4 = isinstance(parsed, dict) and "v4_prompt" in parsed
        except Exception:
            is_v4 = False

    if is_v4:
        result["meta_source"] = "novelai_v4_webp"
        result["format"] = "novelai_v4"
        result["raw_prompt"] = desc_str
        result["raw_meta_json"] = user_comment
    else:
        result["meta_source"] = "novelai_webp"
        result["format"] = "novelai"
        result["raw_prompt"] = desc_str or comment_str
        result["raw_meta_json"] = user_comment

    result["success"] = True
    return result
