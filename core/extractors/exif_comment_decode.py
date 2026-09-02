"""EXIF UserComment decoding and extraction entrypoints."""

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.extractors.exif_decode import decode_exif_user_comment
from core.extractors.exif_raw import extract_user_comment_raw


def extract_exif_user_comment(path: Path) -> str | None:
    try:
        from PIL import Image

        with Image.open(str(path)) as img:
            result = extract_from_pil_image(img)
            if result:
                return result
    except Exception as exc:
        logger.debug("PIL EXIF extraction failed for %s: %s", path, exc)

    try:
        data = path.read_bytes()
        return extract_user_comment_raw(data)
    except Exception:
        return None


def extract_exif_user_comment_from_bytes(data: bytes) -> str | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            result = extract_from_pil_image(img)
            if result:
                return result
    except Exception as exc:
        logger.debug("PIL EXIF extraction from bytes failed: %s", exc)
    return extract_user_comment_raw(data)


def extract_from_pil_image(img) -> str | None:
    try:
        exif = img.getexif()
        if not exif:
            return None
        ifd = exif.get_ifd(0x8769)
        if not ifd:
            return None
        raw = ifd.get(0x9286)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return decode_exif_user_comment(raw)
        if isinstance(raw, str):
            return raw if raw.strip() else None
        return None
    except Exception:
        return None
