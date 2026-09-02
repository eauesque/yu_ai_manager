"""Save generated images to a local folder (NAI bridge wrapper).

Delegates to ``core.bridge_core.bridge_save`` for the actual save logic.
Kept for backward-compatibility with existing imports.
"""

from __future__ import annotations

from core.bridge_core.bridge_save import save_images as _bridge_save


def save_images(
    images: list[bytes],
    seed: int,
    folder: str,
    image_format: str = "png",
    naming: str = "daily_folder",
) -> list[str]:
    """Save image bytes to *folder* and return saved file paths."""
    return _bridge_save(
        images, seed, folder,
        image_format=image_format,
        naming=naming,
    )
