"""Detect whether an image file contains animation (APNG, animated WebP, GIF)."""

import logging
import struct

logger = logging.getLogger(__name__)


def is_animated_image(path_str: str) -> bool | None:
    """Check if an image file is animated.

    Returns True (animated), False (static), or None (unknown/error).
    Only checks PNG (APNG), WebP, and GIF files.
    """
    lower = path_str.lower()
    if lower.endswith(".gif"):
        return True  # All GIFs treated as animated
    if lower.endswith(".png"):
        return _is_apng(path_str)
    if lower.endswith(".webp"):
        return _is_animated_webp(path_str)
    return None


def _is_apng(path_str: str) -> bool:
    """Detect APNG by checking for acTL chunk before IDAT."""
    try:
        with open(path_str, "rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return False
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                length, ctype = struct.unpack(">I4s", header)
                if ctype == b"acTL":
                    return True
                if ctype == b"IDAT" or ctype == b"IEND":
                    return False
                f.seek(length + 4, 1)  # skip data + CRC
    except Exception as exc:
        logger.debug("APNG detection failed: %s", exc)
    return False


def _is_animated_webp(path_str: str) -> bool:
    """Detect animated WebP by checking for ANIM chunk."""
    try:
        with open(path_str, "rb") as f:
            header = f.read(12)
            if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
                return False
            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    break
                fourcc = chunk_header[:4]
                size = struct.unpack("<I", chunk_header[4:8])[0]
                if fourcc == b"ANIM":
                    return True
                # VP8X flags byte: bit 1 = animation
                if fourcc == b"VP8X" and size >= 4:
                    flags_data = f.read(min(size, 4))
                    if len(flags_data) >= 1 and (flags_data[0] & 0x02):
                        return True
                    remaining = size - len(flags_data)
                    if remaining > 0:
                        f.seek(remaining, 1)
                else:
                    f.seek(size, 1)
                # WebP chunks are padded to even size
                if size % 2:
                    f.seek(1, 1)
    except Exception as exc:
        logger.debug("Animated WebP detection failed: %s", exc)
    return False
