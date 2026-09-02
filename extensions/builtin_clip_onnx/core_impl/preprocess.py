"""ONNX CLIP image preprocessing.

Converts images to (1, 3, 224, 224) float32 tensors with CLIP
normalization (ImageNet-style mean/std as used by openai/clip).

cv2 is imported lazily to avoid hard dependency at module load time.
"""

import logging

import numpy as np

from core.clip_core.image_io import read_and_decode

logger = logging.getLogger(__name__)

# CLIP (openai/clip-vit-base-patch16) normalization constants
_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
_TARGET_SIZE = (224, 224)


def preprocess_image(path: str) -> np.ndarray:
    """Load and preprocess an image for ONNX CLIP inference.

    Args:
        path: Image file path (or archive!member path).

    Returns:
        (1, 3, 224, 224) float32 array, normalized.
    """
    import cv2

    img_bgr = read_and_decode(path)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_resized = cv2.resize(img_rgb, _TARGET_SIZE, interpolation=cv2.INTER_LINEAR)

    # float32 [0, 1] -> normalize -> HWC -> CHW
    arr = img_resized.astype(np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    arr = arr.transpose(2, 0, 1)  # HWC -> CHW
    return arr[np.newaxis, ...]  # (1, 3, 224, 224)


def preprocess_images_batch(paths: list) -> tuple:
    """Preprocess a batch of images for ONNX CLIP inference.

    Returns:
        (images, valid_indices) where images is (N, 3, 224, 224) float32
        and valid_indices are the original indices of successfully loaded images.
    """
    import cv2

    images = []
    valid_indices = []
    for i, path in enumerate(paths):
        try:
            img = preprocess_image(path)
            images.append(img[0])  # Remove batch dim
            valid_indices.append(i)
        except (ValueError, cv2.error) as exc:
            logger.warning("Skipping image %s: %s", path, exc)
    if not images:
        return np.empty((0, 3, *_TARGET_SIZE), dtype=np.float32), []
    return np.stack(images), valid_indices
