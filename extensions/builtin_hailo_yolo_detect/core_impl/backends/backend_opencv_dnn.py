"""OpenCV DNN YOLO backend implementation.

Lightest fallback — CPU only, no extra dependencies beyond cv2
which is already a core dependency of the project.
"""

import logging

import cv2
import numpy as np

from .backend_registry import register_backend
from .base import YoloBackend

logger = logging.getLogger(__name__)


@register_backend
class OpenCVDnnYoloBackend(YoloBackend):
    """OpenCV DNN YOLO backend (CPU only, lowest priority fallback)."""

    name = "opencv_dnn"

    def __init__(self) -> None:
        self._net = None
        self._model_name: str = ""
        self._input_size: int = 640

    @staticmethod
    def is_available() -> bool:
        """Check if cv2.dnn is available (always True with OpenCV)."""
        return hasattr(cv2, "dnn")

    @staticmethod
    def priority() -> int:
        """Lowest priority — last resort fallback."""
        return 10

    @staticmethod
    def supported_models() -> list[str]:
        from .backend_onnx import ONNX_MODELS
        return list(ONNX_MODELS.keys())

    def load_model(self, model_name: str, input_size: int = 640) -> None:
        """Load an ONNX YOLO model via cv2.dnn, downloading if needed.

        Shares the ONNX model cache with backend_onnx.

        Args:
            model_name: Key in ONNX_MODELS (e.g. "yolov8n").
            input_size: Model input dimension (overridden by model config).
        """
        if self._net is not None and self._model_name == model_name:
            return  # Already loaded

        # Import model info and download helper from the ONNX backend
        from .backend_onnx import _CACHE_DIR, ONNX_MODELS, _download_model

        info = ONNX_MODELS.get(model_name)
        if info is None:
            raise ValueError(
                f"Unknown model: {model_name}. "
                f"Supported: {list(ONNX_MODELS.keys())}"
            )

        self._input_size = info["input_size"]
        fname = info.get("filename", f"{model_name}.onnx")
        model_path = _CACHE_DIR / fname

        if not model_path.exists():
            _download_model(info["url"], model_path)

        logger.info(
            "Loading ONNX model via cv2.dnn: %s from %s",
            model_name, model_path,
        )

        net = cv2.dnn.readNetFromONNX(str(model_path))
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

        self._net = net
        self._model_name = model_name

        logger.info(
            "OpenCV DNN YOLO model loaded: %s (CPU)", model_name,
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
        """Run YOLO detection via OpenCV DNN.

        Args:
            image: (H, W, 3) uint8 RGB, already letterbox-resized to input_size.
            scale_info: From yolo_preprocess.letterbox_resize.
            conf_threshold: Minimum confidence.
            iou_threshold: NMS IoU threshold.

        Returns:
            List of detection dicts (class_id, class_name, confidence, bbox).
        """
        if self._net is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        from . import postprocess_common

        # Preprocess: HWC uint8 RGB -> NCHW float32 [0, 1]
        # swapRB=False because the image is already RGB
        blob = cv2.dnn.blobFromImage(
            image, 1 / 255.0,
            (self._input_size, self._input_size),
            swapRB=False, crop=False,
        )

        # Run forward pass
        self._net.setInput(blob)
        outputs = self._net.forward()

        # YOLOv8/YOLO11 output: (1, 84, 8400)
        # 84 = 4 box coords (xywh) + 80 class scores
        raw = outputs[0]  # (84, 8400)
        raw = raw.T  # (8400, 84)

        boxes_xywh = raw[:, :4]  # (8400, 4)
        class_scores = raw[:, 4:]  # (8400, 80)

        return postprocess_common.build_detections(
            boxes_xywh,
            class_scores,
            conf_threshold,
            iou_threshold,
            scale_info=scale_info,
        )

    def close(self) -> None:
        """Release the DNN network."""
        if self._net is not None:
            self._net = None
            logger.info("OpenCV DNN YOLO backend closed")
