"""CLIP image preprocessing for Hailo-10H inference.

Hailo HEF expects uint8 (224, 224, 3) input. The HEF internally handles
normalization, so we only need resize + format conversion.

Supports reading from plain files and archive members (ZIP/7z).
"""

import logging

import numpy as np

from core.clip_core.image_io import read_and_decode

logger = logging.getLogger(__name__)


def preprocess_image(path: str, target_size: tuple = (224, 224)) -> np.ndarray:
    """Load and preprocess an image for CLIP inference.

    Handles plain files and archive members (ZIP/7z).

    Args:
        path: path to the image file (or archive!member path)
        target_size: (width, height) for resize

    Returns:
        (H, W, 3) uint8 numpy array in RGB order

    Raises:
        ValueError: if the image cannot be loaded or decoded
    """
    import cv2

    img_bgr = read_and_decode(path)
    img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, target_size, interpolation=cv2.INTER_LINEAR)
    return img.astype(np.uint8)


def preprocess_images_batch(
    paths: list,
    target_size: tuple = (224, 224),
) -> tuple:
    """Preprocess a batch of images.

    Returns:
        (images, valid_indices) where images is (N, H, W, 3) uint8
        and valid_indices are the original indices of successfully loaded images.
    """
    import cv2

    images = []
    valid_indices = []
    for i, path in enumerate(paths):
        try:
            img = preprocess_image(path, target_size)
            images.append(img)
            valid_indices.append(i)
        except (ValueError, cv2.error) as exc:
            logger.warning("Skipping image %s: %s", path, exc)
    if not images:
        return np.empty((0, *target_size, 3), dtype=np.uint8), []
    return np.stack(images), valid_indices
