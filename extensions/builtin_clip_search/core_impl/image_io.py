"""Image I/O utilities for CLIP preprocessing.

Reads image bytes from plain files and archive members (ZIP/7z/RAR) via
the shared ``archive_member_temp`` helpers, then decodes to numpy arrays
via OpenCV.

cv2 is imported lazily so that modules depending on image_io
can be loaded even if opencv-python is not installed.
"""

import logging
from contextlib import contextmanager, suppress

import numpy as np

from core.helpers_core.archive_member_temp import (
    extracted_archive_member_path,
    read_archive_member_bytes,
)

logger = logging.getLogger(__name__)

_cv2_log_silenced = False
_MAX_IMAGE_BYTES = 64 * 1024 * 1024


def read_image_bytes(path: str) -> bytes:
    """Read raw image bytes from a file path (plain or archive member).

    Reads ``_MAX_IMAGE_BYTES`` at call time so tests can monkeypatch the
    module-level constant to exercise the size-cap branch.
    """
    return read_archive_member_bytes(path, max_size_bytes=_MAX_IMAGE_BYTES)


@contextmanager
def open_image_path(path: str):
    """Yield a filesystem path for a plain file or archive member image."""
    with extracted_archive_member_path(
        path, max_size_bytes=_MAX_IMAGE_BYTES,
    ) as fp:
        yield fp


def decode_image(data: bytes) -> np.ndarray:
    """Decode image bytes to BGR numpy array using OpenCV.

    Falls back to Pillow for GIFs and other formats that OpenCV may reject.
    """
    import cv2

    global _cv2_log_silenced
    if not _cv2_log_silenced:
        # Suppress OpenCV's C++ stderr (GIF bgColor, libpng header, etc.)
        with suppress(AttributeError):
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
        _cv2_log_silenced = True

    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is not None:
        return img

    # Fallback: try Pillow (handles broken GIFs, etc.)
    try:
        import io

        from PIL import Image

        pil_img = Image.open(io.BytesIO(data))
        pil_img = pil_img.convert("RGB")
        arr = np.array(pil_img)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception:
        logger.debug("PIL decode failed; trying the next reader", exc_info=True)

    raise ValueError("Failed to decode image from bytes")


def read_and_decode(path: str) -> np.ndarray:
    """Read and decode an image from path to BGR numpy array.

    Handles plain files and archive members (ZIP/7z).
    """
    with open_image_path(path) as resolved:
        try:
            import cv2

            img = cv2.imread(resolved, cv2.IMREAD_COLOR)
            if img is not None:
                return img
        except Exception:
            logger.debug("image decode failed", exc_info=True)

        with open(resolved, "rb") as f:
            data = f.read()
        return decode_image(data)
