"""ONNX Runtime CLIP image encoder.

Singleton wrapper around an ONNX Runtime InferenceSession for the
CLIP ViT-B/16 vision model. Uses ``core.inference_core.ort_provider``
for automatic GPU/NPU/CPU provider selection.
"""

import contextlib
import logging
import threading
from typing import Optional

import numpy as np

from core.clip_core.encoder_abc import ClipImageEncoder

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: Optional["OnnxClipEncoder"] = None


class OnnxClipEncoder(ClipImageEncoder):
    """ONNX Runtime CLIP ViT-B/16 image encoder.

    Thread-safe singleton. Call ``get_encoder()`` to obtain the instance.
    """

    def __init__(self, model_path: str, providers: list[str]):
        import onnxruntime as ort

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self._session = ort.InferenceSession(
            model_path, sess_options=sess_opts, providers=providers,
        )
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        active = self._session.get_providers()
        self._provider = active[0] if active else "CPUExecutionProvider"

        logger.info(
            "ONNX CLIP encoder initialized: %s (provider: %s)",
            model_path,
            self._provider,
        )
        try:
            from extensions.builtin_inference.core_impl.ort_provider import register_active_session
            register_active_session("clip_image", self._session, model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)

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

        outputs = self._session.run(
            [self._output_name],
            {self._input_name: image.astype(np.float32)},
        )
        vec = outputs[0].flatten().astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 1e-12:
            vec = vec / norm
        return vec

    def encode_batch(self, images: np.ndarray) -> np.ndarray:
        """Encode a batch of preprocessed images.

        Args:
            images: (N, 3, 224, 224) float32 array, or (N, 1, 3, 224, 224).

        Returns:
            (N, 512) float32 L2-normalized vectors.
        """
        if images.ndim == 5 and images.shape[1] == 1:
            images = images.squeeze(1)

        outputs = self._session.run(
            [self._output_name],
            {self._input_name: images.astype(np.float32)},
        )
        vecs = outputs[0].astype(np.float32)
        # L2 normalize each vector
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1.0, norms)
        return vecs / norms

    def close(self) -> None:
        """Release the ONNX Runtime session."""
        if hasattr(self, "_session"):
            del self._session
            logger.info("ONNX CLIP encoder closed")

    @property
    def output_dim(self) -> int:
        return 512

    @property
    def backend_name(self) -> str:
        return f"onnx-{self._provider}"


def get_encoder() -> OnnxClipEncoder:
    """Get or create the singleton OnnxClipEncoder.

    Raises:
        RuntimeError: if model is not downloaded or onnxruntime is missing.
    """
    global _instance
    if _instance is not None:
        return _instance

    with _lock:
        if _instance is not None:
            return _instance

        from .model_download import is_model_downloaded, resolve_existing_model_path

        if not is_model_downloaded():
            raise RuntimeError(
                "CLIP ONNX model not downloaded. "
                "Use the model download API or run: "
                "python -c \"from core.clip_onnx_core.model_download import download_model; download_model()\""
            )

        model_path = str(resolve_existing_model_path())

        try:
            from importlib import import_module
            _ort_mod = import_module("extensions.builtin_inference.core_impl.ort_provider")
            select_providers = _ort_mod.select_providers
            providers = select_providers()
        except Exception:
            providers = ["CPUExecutionProvider"]

        _instance = OnnxClipEncoder(model_path, providers)

    return _instance


def close_encoder() -> None:
    """Close the singleton encoder and release resources."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
            _instance = None


def is_onnx_available() -> bool:
    """Check if ONNX CLIP is available (model downloaded + onnxruntime installed)."""
    # A probe: an optional CUDA-only setup step.
    with contextlib.suppress(Exception):
        from core.platform import register_nvidia_dll_dirs

        register_nvidia_dll_dirs()

    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False

    from .model_download import is_model_downloaded
    return is_model_downloaded()
