"""YOLO image preprocessing helpers."""

from __future__ import annotations

import numpy as np


def preprocess_yolo_image(
    image_data: bytes, input_size: int = 640
) -> tuple[np.ndarray, dict]:
    """Letterbox-resize image bytes for YOLO."""
    import cv2

    buf = np.frombuffer(image_data, dtype=np.uint8)
    img_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Failed to decode image")

    height, width = img_bgr.shape[:2]
    scale = min(input_size / height, input_size / width)
    new_width = int(width * scale)
    new_height = int(height * scale)
    resized = cv2.resize(img_bgr, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    pad_x = (input_size - new_width) // 2
    pad_y = (input_size - new_height) // 2

    canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    canvas[pad_y : pad_y + new_height, pad_x : pad_x + new_width] = resized
    canvas_rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)

    scale_info = {
        "orig_h": height,
        "orig_w": width,
        "scale": scale,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "target_size": input_size,
    }
    return canvas_rgb, scale_info
