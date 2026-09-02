"""Core ML CLIP image encoder for Apple Neural Engine.

Singleton wrapper around a Core ML ``MLModel`` for the CLIP ViT-B/16
vision model. Uses ``compute_units=ALL`` to enable Apple Neural Engine
dispatch on supported hardware.
"""

import logging
import sys
import threading
from typing import Optional

import numpy as np

from core.clip_core.encoder_abc import ClipImageEncoder

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: Optional["CoremlClipEncoder"] = None


class CoremlClipEncoder(ClipImageEncoder):
    """Core ML CLIP ViT-B/16 image encoder.

    Thread-safe singleton. Call ``get_encoder()`` to obtain the instance.
    """

    def __init__(self, model_path: str):
        import coremltools as ct

        self._model = ct.models.MLModel(
            model_path,
            compute_units=ct.ComputeUnit.ALL,
        )

        # Discover input/output names from model spec
        spec = self._model.get_spec()
        self._input_name = spec.description.input[0].name
        self._output_name = spec.description.output[0].name

        logger.info(
            "Core ML CLIP encoder initialized: %s (compute_units=ALL)",
            model_path,
        )

    def encode(self, image: np.ndarray) -> np.ndarray:
        """Encode a single preprocessed image to a float32 vector.

        Args:
            image: (1, 3, 224, 224) float32 array, CLIP-normalized.

        Returns:
            (512,) float32 L2-normalized vector.
        """
        # Accept both (1,3,H,W) and (3,H,W)
        if image.ndim == 3:
            image = image[np.newaxis, ...]

        prediction = self._model.predict(
            {self._input_name: image.astype(np.float32)},
        )
        vec = np.array(prediction[self._output_name]).flatten().astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 1e-12:
            vec = vec / norm
        return vec

    def encode_batch(self, images: np.ndarray) -> np.ndarray:
        """Encode a batch of preprocessed images.

        Attempts batch prediction first. Falls back to sequential
        processing if the model does not support dynamic batch sizes.

        Args:
            images: (N, 3, 224, 224) float32 array, or (N, 1, 3, 224, 224).

        Returns:
            (N, 512) float32 L2-normalized vectors.
        """
        if images.ndim == 5 and images.shape[1] == 1:
            images = images.squeeze(1)

        # Try batch prediction
        try:
            prediction = self._model.predict(
                {self._input_name: images.astype(np.float32)},
            )
            vecs = np.array(prediction[self._output_name]).astype(np.float32)
            if vecs.ndim == 1:
                # Model returned flat output for single image
                vecs = vecs.reshape(1, -1)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms = np.where(norms < 1e-12, 1.0, norms)
            return vecs / norms
        except Exception:
            logger.debug("Batch prediction failed, falling back to sequential")
            return np.stack([self.encode(img) for img in images])

    def close(self) -> None:
        """Release the Core ML model."""
        if hasattr(self, "_model"):
            del self._model
            logger.info("Core ML CLIP encoder closed")

    @property
    def output_dim(self) -> int:
        return 512

    @property
    def backend_name(self) -> str:
        return "coreml-ane"


def get_encoder() -> CoremlClipEncoder:
    """Get or create the singleton CoremlClipEncoder.

    On first call, converts the ONNX model to Core ML format if needed.

    Raises:
        RuntimeError: if coremltools is not installed, not on macOS,
                      or model conversion fails.
    """
    global _instance
    if _instance is not None:
        return _instance

    with _lock:
        if _instance is not None:
            return _instance

        if sys.platform != "darwin":
            raise RuntimeError("Core ML backend is only available on macOS")

        from .model_convert import ensure_coreml_model
        model_path = str(ensure_coreml_model())

        _instance = CoremlClipEncoder(model_path)

    return _instance


def close_encoder() -> None:
    """Close the singleton encoder and release resources."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
            _instance = None


def is_coreml_available() -> bool:
    """Check if Core ML CLIP is available.

    Requirements:
    - macOS platform
    - coremltools installed
    - ONNX source model or cached Core ML model exists
    """
    if sys.platform != "darwin":
        return False

    try:
        import coremltools  # noqa: F401
    except ImportError:
        return False

    from .model_convert import is_coreml_model_cached
    if is_coreml_model_cached():
        return True

    # CoreML model not cached yet — check if ONNX source is available
    # so we can convert on first use
    try:
        from core.clip_onnx_core.model_download import is_model_downloaded
        return is_model_downloaded()
    except Exception:
        return False
