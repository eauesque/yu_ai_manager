"""Hailo-10H YOLO backend implementation.

Wraps the existing Hailo inference pipeline into the YoloBackend
interface so it can be used via the backend registry.
"""

import contextlib
import faulthandler
import logging
import threading

import numpy as np

from .backend_registry import register_backend
from .base import YoloBackend

logger = logging.getLogger(__name__)

_OWNER = "yolo"


@register_backend
class HailoBackend(YoloBackend):
    """Hailo-10H accelerated YOLO backend."""

    name = "hailo"

    def __init__(self) -> None:
        self._model_name: str = ""
        self._input_size: int = 640
        self._infer_model = None
        self._configured = None
        self._quant_params_list: list = []
        self._output_shapes: list = []
        # Pre-allocated bindings, input buffer, and output buffers to avoid per-frame
        # CMA allocation.  create_bindings()/set_buffer() map DMA-able CMA pages;
        # calling set_buffer() with a *new* numpy array each frame re-registers a new
        # DMA mapping and leaks CMA (HailoRT 5.3.0 does not release old mappings via GC).
        # Fix: allocate BOTH input and output buffers once in load_model(), then
        # np.copyto() the frame data into the pre-allocated input buffer in detect().
        self._bindings = None
        self._input_buffer: np.ndarray | None = None
        self._output_buffers: list = []
        # Mutex: serialises concurrent detect() calls (stream pipeline vs batch
        # detection) and guards close() so the backend is never torn down mid-inference.
        self._infer_lock = threading.Lock()

    @staticmethod
    def is_available() -> bool:
        """Check if Hailo hardware is accessible."""
        try:
            from core.hailo_device_core.device_manager import (
                is_hailo_available,
            )
            return is_hailo_available()
        except Exception:
            return False

    @staticmethod
    def priority() -> int:
        return 100

    @staticmethod
    def supported_models() -> list[str]:
        """Return model names from the YOLO model registry."""
        from ..model_download import YOLO_MODELS
        return list(YOLO_MODELS.keys())

    def load_model(self, model_name: str, input_size: int = 640) -> None:
        """Load a YOLO HEF model onto the Hailo device.

        Args:
            model_name: Key in YOLO_MODELS (e.g. "yolov8n").
            input_size: Model input dimension.
        """
        from core.hailo_device_core.device_manager import acquire_device

        from ..model_download import YOLO_MODELS, get_hef_path

        # Release previous model if switching
        if self._infer_model is not None and self._model_name != model_name:
            self.close()

        info = YOLO_MODELS.get(model_name)
        if info:
            input_size = info["input_size"]

        hef_path = get_hef_path(model_name)
        if not hef_path.exists():
            raise FileNotFoundError(
                f"YOLO HEF not found: {hef_path}. "
                f"Download it first via the UI or API."
            )

        infer_model, configured, quant_params_list = acquire_device(
            _OWNER, str(hef_path),
        )

        self._infer_model = infer_model
        self._configured = configured
        self._quant_params_list = quant_params_list
        self._model_name = model_name
        self._input_size = input_size
        self._output_shapes = [
            tuple(o.shape) for o in infer_model.outputs
        ]

        logger.info(
            "Hailo YOLO model loaded: %s (%s), %d output tensors",
            model_name, hef_path, len(self._output_shapes),
        )
        for i, (s, qp) in enumerate(
            zip(self._output_shapes, quant_params_list, strict=False)
        ):
            logger.info(
                "  Output %d: shape=%s dtype=%s scale=%.6f zp=%.1f",
                i, s, qp.get("dtype", "uint8"),
                qp["scale"], qp["zero_point"],
            )

        # Pre-allocate bindings, input buffer, and output buffers once.
        # Both input and output set_buffer() calls are made here so that HailoRT
        # registers the DMA mappings once; detect() only copies frame data into
        # the pre-allocated input buffer without creating new CMA mappings.
        self._bindings = configured.create_bindings()

        # Input buffer — shape comes from the model so we never hard-code it.
        try:
            inp = infer_model.input  # single-input model
            input_shape = tuple(inp.shape)
        except AttributeError:
            # Fallback: use configured input_size (always uint8 HWC for YOLO)
            input_shape = (input_size, input_size, 3)
        self._input_buffer = np.empty(input_shape, dtype=np.uint8)
        self._bindings.input().set_buffer(self._input_buffer)

        self._output_buffers = []
        for i, out in enumerate(infer_model.outputs):
            dtype_str = quant_params_list[i].get("dtype", "uint8")
            np_dtype = np.float32 if dtype_str == "float32" else np.uint8
            buf = np.empty(tuple(out.shape), dtype=np_dtype)
            self._bindings.output(out.name).set_buffer(buf)
            self._output_buffers.append(buf)
        logger.info(
            "Hailo YOLO: pre-allocated input buffer %s + %d output buffers",
            input_shape, len(self._output_buffers),
        )

    @property
    def input_size(self) -> int:
        return self._input_size

    @property
    def model_name(self) -> str:
        return self._model_name

    def detect(
        self,
        image: np.ndarray,
        scale_info: dict | None = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> list[dict]:
        """Run YOLO detection via Hailo-10H.

        Args:
            image: (H, W, 3) uint8 RGB, already letterbox-resized.
            scale_info: From yolo_preprocess.letterbox_resize.
            conf_threshold: Minimum confidence.
            iou_threshold: NMS IoU threshold.

        Returns:
            List of detection dicts (class_id, class_name, confidence, bbox).
        """
        with self._infer_lock:
            if self._configured is None or self._bindings is None:
                raise RuntimeError("No model loaded. Call load_model() first.")

            from ..yolo_postprocess import postprocess_yolo_outputs

            # Arm a C-level SIGALRM watchdog so the process exits via faulthandler
            # if configured.run() hangs indefinitely (HailoRT C extension can hold
            # the GIL and block the asyncio event loop).  This watchdog also covers
            # batch-detection callers that don't go through stream_pipeline.py.
            with contextlib.suppress(Exception):
                faulthandler.dump_traceback_later(15, exit=True)
            try:
                # Copy frame data into the pre-allocated input buffer.
                # This avoids calling set_buffer() with a new array each frame, which
                # would register a fresh DMA mapping and slowly exhaust CMA
                # (HailoRT 5.3.0 bug).
                self._input_buffer[...] = image
                self._configured.run([self._bindings], timeout=10000)
            finally:
                with contextlib.suppress(Exception):
                    faulthandler.cancel_dump_traceback_later()

            return postprocess_yolo_outputs(
                buffers=self._output_buffers,
                quant_params=self._quant_params_list,
                conf_threshold=conf_threshold,
                iou_threshold=iou_threshold,
                input_size=self._input_size,
                scale_info=scale_info,
            )

    def close(self) -> None:
        """Release the Hailo device.

        Acquires _infer_lock so that any in-flight detect() call completes
        before the backend is torn down.  Uses a 5 s timeout so that a hung
        detect() does not block shutdown indefinitely.
        """
        acquired = self._infer_lock.acquire(timeout=5.0)
        try:
            if self._infer_model is not None:
                from core.hailo_device_core.device_manager import release_device
                release_device(_OWNER)
                self._infer_model = None
                self._configured = None
                self._bindings = None
                self._input_buffer = None
                self._output_buffers = []
                self._quant_params_list = []
                self._output_shapes = []
                logger.info("Hailo YOLO backend closed")
        finally:
            if acquired:
                self._infer_lock.release()
