"""Image resize for Bluesky (PIL, 1MB limit)."""

import io
import logging

logger = logging.getLogger(__name__)

_MAX_SIZE_BYTES = 1_000_000  # Bluesky 1MB limit
_MAX_DIMENSION = 2048


def prepare_image_for_bluesky(
    image_path: str,
    max_bytes: int = _MAX_SIZE_BYTES,
) -> tuple[bytes | None, str]:
    """Resize and compress an image for Bluesky posting.

    Returns:
        (image_bytes, mime_type) -- on failure (None, error_message)
    """
    try:
        from PIL import Image
    except ImportError:
        return None, "Pillow is not installed"

    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.warning("Failed to open image %s: %s", image_path, exc)
        return None, f"Failed to open image: {exc}"

    # RGBA -> RGB (for JPEG)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize longest edge to 2048px
    w, h = img.size
    if max(w, h) > _MAX_DIMENSION:
        ratio = _MAX_DIMENSION / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # Gradually reduce JPEG quality to fit under 1MB
    for quality in (92, 85, 75, 60, 45):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data, "image/jpeg"

    # If still too large, shrink further
    ratio = 0.7
    for _ in range(3):
        w, h = img.size
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60, optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data, "image/jpeg"

    return None, "Image too large even after aggressive compression"
