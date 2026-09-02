"""Image preprocessing primitives shared across adapters.

Spec reference:
  docs/superpowers/specs/2026-05-10-tagger-pluggable-models-design.md
  § 4.1 (file responsibilities), § 5.4 (preprocess_spec).
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image


def _load_and_pad(
    image_path: str,
    size: int,
    pad_color: tuple[int, int, int],
) -> Image.Image:
    """Load image, preserve aspect ratio, and pad to a square canvas.

    Accepts both plain filesystem paths and archive member paths
    (``archive.zip!entry``, ``.7z!``, ``.rar!``). DB-stored file paths
    transparently include archive members, so the adapter must resolve
    them before handing off to PIL.
    """
    from core.helpers_core.archive_member_temp import extracted_archive_member_path

    with (
        extracted_archive_member_path(image_path) as real_path,
        Image.open(real_path) as raw,
    ):
        img = raw.convert("RGBA")

    bg = Image.new("RGBA", img.size, (*pad_color, 255))
    bg.alpha_composite(img)
    img = bg.convert("RGB")

    old_w, old_h = img.size
    scale = size / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    padded = Image.new("RGB", (size, size), pad_color)
    padded.paste(img, ((size - new_w) // 2, (size - new_h) // 2))
    return padded


def preprocess_image_wd_recipe(image_path: str, size: int = 448) -> np.ndarray:
    """WD-Tagger preprocessing recipe.

    Produces NHWC float32 batch input with BGR channel order and no scaling.
    """
    padded = _load_and_pad(image_path, size, pad_color=(255, 255, 255))
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]
    return np.expand_dims(arr, axis=0)


def preprocess_image_from_spec(image_path: str, spec: dict[str, Any]) -> np.ndarray:
    """Preprocess an image according to a profile preprocess_spec dict."""
    size = int(spec["input_size"])
    pad_color = tuple(spec.get("pad_color", [255, 255, 255]))

    strategy = spec.get("resize_strategy", "longest_side_pad")
    if strategy != "longest_side_pad":
        raise NotImplementedError(
            f"resize_strategy={strategy!r} not supported in Phase 1a"
        )

    padded = _load_and_pad(
        image_path,
        size,
        pad_color,  # type: ignore[arg-type]
    )
    arr = np.array(padded, dtype=np.float32)

    if spec.get("channel_order", "RGB") == "BGR":
        arr = arr[:, :, ::-1]

    scale = float(spec.get("scale", 1.0))
    if scale != 1.0:
        arr = arr * scale

    mean = spec.get("mean")
    if mean is not None:
        arr = arr - np.array(mean, dtype=np.float32)

    std = spec.get("std")
    if std is not None:
        std_arr = np.array(std, dtype=np.float32)
        if (std_arr == 0).any():
            raise ValueError(
                "preprocess_spec.std contains zero — division by zero would "
                "produce inf/nan. Use null to skip normalization instead."
            )
        arr = arr / std_arr

    if spec.get("layout", "NHWC") == "NCHW":
        arr = np.transpose(arr, (2, 0, 1))

    return np.expand_dims(arr, axis=0)
