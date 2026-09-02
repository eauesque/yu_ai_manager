"""Camera (Viewport) computation.

Calculates the crop rectangle for each frame from focus position and scale.
"""

from __future__ import annotations

from dataclasses import dataclass

from .focus_provider import get_easing


@dataclass
class Viewport:
    """Crop rectangle on the image (pixel coordinates)."""

    x: int
    y: int
    w: int
    h: int


def compute_viewport(
    t: float,
    focus_x: float,
    focus_y: float,
    img_w: int,
    img_h: int,
    out_w: int,
    out_h: int,
    scale_start: float,
    scale_end: float,
    easing: str = "ease_in_out_cubic",
) -> Viewport:
    """Compute the viewport at time t.

    Args:
        t: Normalized time 0..1
        focus_x, focus_y: Focus position (normalized coordinates 0..1)
        img_w, img_h: Source image size (px)
        out_w, out_h: Output video size (px)
        scale_start: Starting zoom factor (>= 1.0)
        scale_end: Ending zoom factor (>= 1.0, typically 1.0)
        easing: Easing function name for scale interpolation

    Returns:
        Viewport (pixel coordinates)
    """
    ease_fn = get_easing(easing)
    e = ease_fn(max(0.0, min(1.0, t)))
    scale = scale_start + (scale_end - scale_start) * e

    # Crop size (larger scale = smaller crop = zoom in)
    out_aspect = out_w / out_h
    crop_h = img_h / scale
    crop_w = crop_h * out_aspect

    # Adjust if crop exceeds source image
    if crop_w > img_w:
        crop_w = float(img_w)
        crop_h = crop_w / out_aspect
    if crop_h > img_h:
        crop_h = float(img_h)
        crop_w = crop_h * out_aspect

    # Position crop centered on focus point
    cx = focus_x * img_w
    cy = focus_y * img_h

    x = cx - crop_w / 2
    y = cy - crop_h / 2

    # Clamp (do not exceed image bounds)
    x, y = clamp_viewport(x, y, crop_w, crop_h, img_w, img_h)

    return Viewport(
        x=int(round(x)),
        y=int(round(y)),
        w=int(round(crop_w)),
        h=int(round(crop_h)),
    )


def clamp_viewport(
    x: float, y: float,
    crop_w: float, crop_h: float,
    img_w: int, img_h: int,
) -> tuple[float, float]:
    """Clamp viewport to image boundaries."""
    if x < 0:
        x = 0.0
    if y < 0:
        y = 0.0
    if x + crop_w > img_w:
        x = img_w - crop_w
    if y + crop_h > img_h:
        y = img_h - crop_h
    # Final safety check
    x = max(0.0, x)
    y = max(0.0, y)
    return x, y
