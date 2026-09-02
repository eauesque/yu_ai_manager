"""Common image-saving logic for all bridge extensions."""

from __future__ import annotations

import io
import logging
import os
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

NAMING_PATTERNS = ["daily_folder", "date_prefix", "timestamp"]
IMAGE_FORMATS = ("png", "webp", "jpg")

# PNG magic bytes / WebP RIFF header / JPEG SOI marker
_PNG_MAGIC = b"\x89PNG"
_WEBP_MAGIC = b"RIFF"
_JPEG_MAGIC = b"\xff\xd8"


def _detect_format(data: bytes) -> str:
    """Detect image format from magic bytes."""
    if data[:4] == _PNG_MAGIC:
        return "png"
    if data[:4] == _WEBP_MAGIC and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == _JPEG_MAGIC:
        return "jpg"
    return "unknown"


def _build_exif_user_comment(text_chunks: dict[str, str]) -> bytes | None:
    """Build minimal EXIF bytes with UserComment containing PNG text metadata.

    Constructs a valid EXIF APP1 segment without external dependencies.
    The UserComment is encoded as UNICODE so that metadata parsers (including
    this project's own extractors) can read it back from WebP/JPEG files.

    Format: JSON-encoded dict prefixed with "YU_META:" marker for reliable
    round-trip parsing. Falls back to "key: value" format for legacy compat.
    """
    try:
        import json
        comment = "YU_META:" + json.dumps(text_chunks, ensure_ascii=False)
        comment_bytes = comment.encode("utf-16-le")

        # UserComment = 8-byte charset ID + payload
        # "UNICODE\x00" prefix signals UTF-16 encoding
        user_comment_value = b"UNICODE\x00" + comment_bytes

        # Build IFD entry for ExifIFD pointer (tag 0x8769)
        # and Exif sub-IFD with UserComment (tag 0x9286)
        import struct

        # Use little-endian ("II") TIFF header
        tiff_header = b"II"  # little-endian
        tiff_header += struct.pack("<H", 42)  # TIFF magic

        # IFD0 starts at offset 8
        ifd0_offset = 8
        tiff_header += struct.pack("<I", ifd0_offset)

        # IFD0: 1 entry (ExifIFD pointer)
        ifd0_count = struct.pack("<H", 1)
        # Tag 0x8769 (ExifIFD), Type LONG(4), Count 1, Value = offset to Exif IFD
        exif_ifd_offset = 8 + 2 + 12 + 4  # header + count + 1 entry + next_ifd
        ifd0_entry = struct.pack("<HHII", 0x8769, 4, 1, exif_ifd_offset)
        ifd0_next = struct.pack("<I", 0)  # no next IFD

        # Exif IFD: 1 entry (UserComment)
        exif_ifd_count = struct.pack("<H", 1)
        uc_len = len(user_comment_value)
        # Data offset: after Exif IFD (count + 1 entry + next_ifd)
        uc_data_offset = exif_ifd_offset + 2 + 12 + 4
        # Tag 0x9286, Type UNDEFINED(7), Count = byte length
        exif_ifd_entry = struct.pack("<HHII", 0x9286, 7, uc_len, uc_data_offset)
        exif_ifd_next = struct.pack("<I", 0)

        tiff_body = (ifd0_count + ifd0_entry + ifd0_next
                     + exif_ifd_count + exif_ifd_entry + exif_ifd_next
                     + user_comment_value)

        exif_bytes = b"Exif\x00\x00" + tiff_header + tiff_body
        return exif_bytes
    except Exception as exc:
        logger.warning("EXIF build failed: %s", exc)
        return None


def _extract_metadata(pil_img, raw_data: bytes) -> dict[str, str]:
    """Extract generation metadata from any supported image format.

    Returns a dict of key-value pairs suitable for embedding in any target format.
    Supports: PNG tEXt chunks, WebP/JPEG EXIF UserComment.
    """
    # 1. PNG tEXt chunks (most common for SD WebUI / NAI)
    if hasattr(pil_img, "text") and isinstance(pil_img.text, dict) and pil_img.text:
        return dict(pil_img.text)

    # 2. EXIF UserComment (WebP / JPEG from bridge conversion)
    try:
        exif_bytes = pil_img.info.get("exif", b"")
        if not exif_bytes:
            return {}
        from core.extractors.exif_user_comment import _parse_exif_user_comment
        comment = _parse_exif_user_comment(exif_bytes)
        if comment:
            # YU_META: prefix = JSON-encoded dict (written by _build_exif_user_comment)
            if comment.startswith("YU_META:"):
                import json
                try:
                    return json.loads(comment[8:])
                except (json.JSONDecodeError, ValueError):
                    pass
            # Legacy "key: value" format fallback
            result: dict[str, str] = {}
            for line in comment.split("\n"):
                sep = line.find(": ")
                if sep > 0:
                    key = line[:sep]
                    val = line[sep + 2:]
                    if key in result:
                        result[key] += "\n" + val
                    else:
                        result[key] = val
                elif result:
                    last_key = list(result.keys())[-1]
                    result[last_key] += "\n" + line
            if result:
                return result
    except Exception:
        logger.warning("step failed", exc_info=True)

    return {}


def _convert_image(data: bytes, target_format: str, extra_fields: dict | None = None) -> bytes:
    """Convert image bytes to *target_format* using PIL.

    Preserves generation metadata across all format conversions:
    PNG tEXt ↔ WebP/JPEG EXIF UserComment.

    If *extra_fields* contains ``_gen_params``, those params are embedded in
    the output image.  The ``_gen_params`` key always overwrites any existing
    ``_gen_params`` value; all other keys in *extra_fields* are ignored.
    Generation metadata already present in the source image (``prompt``,
    ``workflow``, etc.) is always preserved unchanged via ``_extract_metadata``.

    Returns the original bytes unchanged if conversion fails or the image is
    already in the target format and no extra_fields are requested.
    """
    import json

    source = _detect_format(data)
    has_extra = bool(extra_fields and "_gen_params" in extra_fields)
    if source == target_format and not has_extra:
        return data

    try:
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        pil_img = Image.open(io.BytesIO(data))

        # Extract metadata from any source format (PNG, WebP, JPEG)
        text_chunks = _extract_metadata(pil_img, data)

        # Merge extra_fields: _gen_params always overwrites, others are skipped
        if extra_fields:
            for key, value in extra_fields.items():
                if key == "_gen_params":
                    # Serialize dict → JSON string for storage
                    if isinstance(value, dict):
                        # PNG tEXt path will use ensure_ascii=True later
                        # WebP/JPEG path will use ensure_ascii=False later
                        # Store the raw dict here; serialization is per-format below
                        text_chunks[key] = value  # type: ignore[assignment]
                    else:
                        text_chunks[key] = value

        buf = io.BytesIO()
        if target_format == "webp":
            # Serialize _gen_params with ensure_ascii=False for UTF-16-LE EXIF
            serialized: dict[str, str] = {}
            for k, v in text_chunks.items():
                if isinstance(v, dict):
                    serialized[k] = json.dumps(v, ensure_ascii=False)
                else:
                    serialized[k] = v
            exif_bytes = _build_exif_user_comment(serialized) if serialized else None
            pil_img.save(buf, "WEBP", lossless=True,
                         exif=exif_bytes or b"")
        elif target_format == "jpg":
            pil_img = pil_img.convert("RGB")
            # Serialize _gen_params with ensure_ascii=False for UTF-16-LE EXIF
            serialized = {}
            for k, v in text_chunks.items():
                if isinstance(v, dict):
                    serialized[k] = json.dumps(v, ensure_ascii=False)
                else:
                    serialized[k] = v
            exif_bytes = _build_exif_user_comment(serialized) if serialized else None
            pil_img.save(buf, "JPEG", quality=95,
                         exif=exif_bytes or b"")
        else:
            # Preserve as PNG tEXt chunks
            # PNG tEXt is Latin-1; use ensure_ascii=True to keep non-ASCII safe
            png_info = PngInfo()
            for key, value in text_chunks.items():
                if isinstance(value, dict):
                    png_info.add_text(key, json.dumps(value, ensure_ascii=True))
                else:
                    png_info.add_text(key, value)
            pil_img.save(buf, "PNG", pnginfo=png_info)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("Image conversion to %s failed: %s", target_format, exc)
        return data


def save_images(
    images: list[bytes],
    seed: int,
    folder: str,
    image_format: str = "png",
    naming: str = "daily_folder",
    extra_fields: dict | None = None,
) -> list[str]:
    """Save image bytes to *folder* and return the list of saved file paths.

    If the raw image bytes are not already in *image_format*, they are
    automatically converted via PIL before writing.

    *extra_fields* is forwarded to ``_convert_image``.  Pass
    ``{"_gen_params": {...}}`` to embed generation parameters in each saved
    image.

    Naming patterns:
      - ``daily_folder``:  ``<folder>/2026-02-25/42_0.png``
      - ``date_prefix``:   ``<folder>/2026-02-25_143022_42_0.png``
      - ``timestamp``:     ``<folder>/42_1740000000_0.png``  (legacy)
    """
    if not folder:
        return []

    ext = image_format if image_format in IMAGE_FORMATS else "png"
    now = datetime.now(tz=UTC).astimezone()
    ts = int(time.time())

    dest = os.path.join(folder, now.strftime("%Y-%m-%d")) if naming == "daily_folder" else folder

    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as exc:
        logger.error("Failed to create save folder %s: %s", dest, exc)
        return []
    saved: list[str] = []

    for i, img_bytes in enumerate(images):
        # Convert to requested format if needed
        img_bytes = _convert_image(img_bytes, ext, extra_fields=extra_fields)

        if naming == "daily_folder":
            fname = f"{seed}_{i}.{ext}"
        elif naming == "date_prefix":
            fname = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{seed}_{i}.{ext}"
        else:
            # timestamp (legacy)
            fname = f"{seed}_{ts}_{i}.{ext}"

        path = os.path.join(dest, fname)
        # Avoid overwriting existing files
        if os.path.exists(path):
            base, fext = os.path.splitext(path)
            n = 1
            while os.path.exists(f"{base}_{n}{fext}"):
                n += 1
            path = f"{base}_{n}{fext}"

        try:
            with open(path, "wb") as f:
                f.write(img_bytes)
            saved.append(path)
            logger.info("Saved image: %s", path)
        except OSError as exc:
            logger.warning("Failed to save image %s: %s", path, exc)

    return saved
