"""Image conversion helpers for ComfyUI API generation."""

from __future__ import annotations

import base64 as b64mod


def convert_images(images: list, target_format: str) -> list:
    from core.bridge_core.bridge_save import _convert_image

    converted = []
    for img in images:
        try:
            raw = b64mod.b64decode(img["base64"])
            new_b64 = b64mod.b64encode(_convert_image(raw, target_format)).decode("ascii")
            entry = dict(img)
            entry["base64"] = new_b64
            converted.append(entry)
        except Exception:
            converted.append(img)
    return converted
