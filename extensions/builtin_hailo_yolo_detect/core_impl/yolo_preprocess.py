"""YOLO image preprocessing for Hailo-10H inference.

Performs letterbox resize to 640x640 (aspect-ratio preserving with
grey padding) and returns scale info for coordinate back-mapping.

Supports plain files and archive members (ZIP/7z/RAR) via the shared
``archive_member_temp`` helpers — both ``_read_image_bytes`` and
``_open_image_path`` thinly delegate so the cap is enforced once in a
single place.
"""

import logging
from contextlib import contextmanager

import cv2
import numpy as np

from core.helpers_core.archive_member_temp import (
    extracted_archive_member_path,
    read_archive_member_bytes,
)

logger = logging.getLogger(__name__)
_MAX_IMAGE_BYTES = 64 * 1024 * 1024


def _read_image_bytes(path: str) -> bytes:
    """Read raw image bytes from a file path (plain or archive member).

    Reads ``_MAX_IMAGE_BYTES`` at call time so tests can monkeypatch the
    module-level constant to exercise the size-cap branch.
    """
    return read_archive_member_bytes(path, max_size_bytes=_MAX_IMAGE_BYTES)


@contextmanager
def _open_image_path(path: str):
    """Yield a real filesystem path for plain files or archive members."""
    with extracted_archive_member_path(
        path, max_size_bytes=_MAX_IMAGE_BYTES,
    ) as fp:
        yield fp


def _decode_image(data: bytes) -> np.ndarray:
    """Decode image bytes to BGR numpy array."""
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image from bytes")
    return img


def letterbox_resize(
    img: np.ndarray,
    target_size: int = 640,
    pad_value: int = 114,
) -> tuple:
    """Letterbox-resize an image preserving aspect ratio.

    Args:
        img: BGR numpy array (H, W, 3)
        target_size: square target dimension
        pad_value: grey fill value for padding

    Returns:
        (resized_img, scale_info) where scale_info is a dict with:
          - orig_h, orig_w: original dimensions
          - scale: resize scale factor
          - pad_x, pad_y: padding offsets
    """
    h, w = img.shape[:2]
    scale = min(target_size / h, target_size / w)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_x = (target_size - new_w) // 2
    pad_y = (target_size - new_h) // 2

    canvas = np.full(
        (target_size, target_size, 3), pad_value, dtype=np.uint8,
    )
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

    scale_info = {
        "orig_h": h,
        "orig_w": w,
        "scale": scale,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "target_size": target_size,
    }
    return canvas, scale_info


def preprocess_image_yolo(
    path: str,
    target_size: int = 640,
) -> tuple:
    """Load, decode, and letterbox-resize an image for YOLO inference.

    Args:
        path: file path (or archive!member path)
        target_size: square target dimension (default 640)

    Returns:
        (image_rgb, scale_info) where image_rgb is (H, W, 3) uint8 RGB

    Raises:
        ValueError: if the image cannot be loaded or decoded
    """
    with _open_image_path(path) as resolved:
        img_bgr = cv2.imread(resolved, cv2.IMREAD_COLOR)
        if img_bgr is None:
            with open(resolved, "rb") as f:
                data = f.read()
            img_bgr = _decode_image(data)
    canvas_bgr, scale_info = letterbox_resize(img_bgr, target_size)
    canvas_rgb = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2RGB)
    return canvas_rgb, scale_info


def preprocess_frame_yolo(
    frame_bgr: np.ndarray,
    target_size: int = 640,
) -> tuple:
    """Letterbox-resize a BGR frame (already loaded) for YOLO.

    Returns:
        (image_rgb, scale_info)
    """
    canvas_bgr, scale_info = letterbox_resize(frame_bgr, target_size)
    canvas_rgb = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2RGB)
    return canvas_rgb, scale_info
