"""Hailo-10H CLIP image encoder singleton wrapper.

Uses the shared VDevice manager (``core.hailo_device_core``) so that
CLIP and YOLO can share the same physical device with automatic
model switching.

Key constraints (Hailo-10H):
- inputs/outputs are properties, not methods
- Output buffer MUST be uint8 (not float32)
- VDevice is exclusive (conflicts with hailo-ollama)
"""

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from core.clip_core.encoder_abc import ClipImageEncoder

from .dequantize import dequantize, normalize_vector

logger = logging.getLogger(__name__)

_DEFAULT_HEF_DIR = os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models"))
_IMAGE_ENCODER_HEF = "clip_vit_b_16_image_encoder.hef"

_lock = threading.Lock()
_instance: Optional["HailoClipEncoder"] = None

_OWNER = "clip"


class HailoClipEncoder(ClipImageEncoder):
    """Hailo-10H CLIP image encoder.

    Thread-safe singleton. Call get_encoder() to obtain the instance.
    """

    def __init__(self, hef_path: str):
        from core.hailo_device_core.device_manager import acquire_device

        self._hef_path = hef_path
        infer_model, configured, quant_params_list = acquire_device(
            _OWNER, hef_path,
        )
        self._infer_model = infer_model
        self._configured = configured

        # CLIP has a single output
        qp = quant_params_list[0] if quant_params_list else {
            "scale": 1.0, "zero_point": 0.0,
        }
        self._quant_params = {
            "scale": qp["scale"],
            "zero_point": qp["zero_point"],
        }
        logger.info(
            "Hailo CLIP encoder initialized: %s (scale=%.6f, zp=%.1f)",
            hef_path,
            self._quant_params["scale"],
            self._quant_params["zero_point"],
        )

        inp = self._infer_model.inputs[0]
        out = self._infer_model.outputs[0]
        self._input_shape = tuple(inp.shape)
        self._output_shape = tuple(out.shape)
        logger.info(
            "  Input shape: %s, Output shape: %s",
            self._input_shape, self._output_shape,
        )

    @property
    def input_shape(self) -> tuple:
        return self._input_shape

    @property
    def output_dim(self) -> int:
        """Output vector dimensionality (e.g. 512)."""
        dim = 1
        for s in self._output_shape:
            dim *= s
        return dim

    @property
    def backend_name(self) -> str:
        return "hailo-10h"

    def encode(self, image: np.ndarray) -> np.ndarray:
        """Encode a single image to a float32 vector.

        Args:
            image: (H, W, 3) uint8 numpy array

        Returns:
            (dim,) float32 normalized vector
        """
        bindings = self._configured.create_bindings()
        bindings.input().set_buffer(image)

        output_buf = np.empty(self._output_shape, dtype=np.uint8)
        bindings.output().set_buffer(output_buf)

        self._configured.run([bindings], timeout=10000)

        vec_f32 = dequantize(
            output_buf.flatten(),
            self._quant_params["scale"],
            self._quant_params["zero_point"],
        )
        return normalize_vector(vec_f32)

    def encode_batch(self, images: np.ndarray) -> np.ndarray:
        """Encode a batch of images sequentially.

        Args:
            images: (N, H, W, 3) uint8 numpy array

        Returns:
            (N, dim) float32 normalized vectors
        """
        results = []
        for img in images:
            results.append(self.encode(img))
        return np.stack(results)

    def close(self) -> None:
        """Release Hailo device via the shared device manager."""
        from core.hailo_device_core.device_manager import release_device
        release_device(_OWNER)


def get_encoder(hef_dir: str | None = None) -> HailoClipEncoder:
    """Get or create the singleton HailoClipEncoder.

    Args:
        hef_dir: directory containing HEF files. Defaults to ~/hailo_models.

    Raises:
        FileNotFoundError: if the HEF file is not found
        RuntimeError: if Hailo device is unavailable
    """
    global _instance
    if _instance is not None:
        return _instance

    with _lock:
        if _instance is not None:
            return _instance

        hef_dir = hef_dir or _DEFAULT_HEF_DIR
        hef_path = Path(hef_dir) / _IMAGE_ENCODER_HEF
        if not hef_path.exists():
            raise FileNotFoundError(
                f"CLIP image encoder HEF not found: {hef_path}. "
                f"Download from Hailo Model Zoo."
            )

        try:
            _instance = HailoClipEncoder(str(hef_path))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize Hailo device: {exc}. "
                f"Is hailo-ollama running? Try: systemctl stop hailo-ollama"
            ) from exc

    return _instance


def close_encoder() -> None:
    """Close the singleton encoder and release the Hailo device."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
            _instance = None
            logger.info("Hailo CLIP encoder closed")


def is_hailo_available() -> bool:
    """Check if Hailo device and HEF are available (without initializing)."""
    hef_path = Path(_DEFAULT_HEF_DIR) / _IMAGE_ENCODER_HEF
    if not hef_path.exists():
        return False
    from core.hailo_device_core.device_manager import is_hailo_available as _hw_check
    return _hw_check()


def get_hailo_status() -> dict:
    """Return a structured availability report for the CLIP-on-Hailo backend.

    Distinguishes the three failure modes that would otherwise collapse to a
    single bool: missing Python wheel, missing HEF, missing hardware. The
    extension status route surfaces this so the UI can render an actionable
    message instead of an opaque "N/A".
    """
    hef_path = Path(_DEFAULT_HEF_DIR) / _IMAGE_ENCODER_HEF

    try:
        import hailo_platform  # noqa: F401

        runtime_ok = True
    except ImportError:
        runtime_ok = False

    try:
        from core.hailo_device_core.device_manager import is_hailo_available as _hw_check

        hw_ok = bool(_hw_check())
    except Exception:
        hw_ok = False

    hef_ok = hef_path.exists()

    if not runtime_ok:
        reason = "hailo_platform Python wheel not installed"
    elif not hw_ok:
        reason = "Hailo device not detected"
    elif not hef_ok:
        reason = f"CLIP HEF not found: {hef_path}"
    else:
        reason = ""

    return {
        "available": runtime_ok and hw_ok and hef_ok,
        "runtime_ok": runtime_ok,
        "hardware_ok": hw_ok,
        "hef_ok": hef_ok,
        "hef_path": str(hef_path),
        "reason": reason,
    }
