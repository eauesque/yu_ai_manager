"""ONNX Runtime YOLO backend implementation.

Supports CUDA, ROCm, and CPU execution providers with automatic
priority selection based on available hardware.
"""

import logging
import urllib.request
from pathlib import Path

import numpy as np

from core.platform import register_nvidia_dll_dirs

from .backend_registry import register_backend
from .base import YoloBackend

logger = logging.getLogger(__name__)

# Pin venv-bundled CUDA / cuDNN DLLs into the loader cache before any CUDA EP
# code touches the GPU. Without this, system-installed cuDNN (e.g. CUDNN v9.20
# for CUDA 13) can hijack the lazy-loaded sub-libraries and cause Plan -1 /
# CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH failures.
register_nvidia_dll_dirs()

ONNX_MODELS: dict[str, dict] = {
    "yolov11n": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx",
        "filename": "yolo11n.onnx",
        "input_size": 640,
    },
    # yolov8n: use yolo11n ONNX (same output format: 1,84,8400, backward compatible)
    "yolov8n": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx",
        "filename": "yolo11n.onnx",
        "input_size": 640,
    },
}

_CACHE_DIR = Path.home() / ".cache" / "yu_ai_manager" / "yolo_onnx"

# Provider name -> backend priority
_PROVIDER_PRIORITY = {
    "CUDAExecutionProvider": 70,
    "ROCMExecutionProvider": 60,
    "CPUExecutionProvider": 20,
}


def _get_best_provider() -> tuple:
    """Return (provider_name, priority) for the best available EP.

    Returns:
        Tuple of (provider_name, priority_int).
    """
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
    except Exception:
        return ("CPUExecutionProvider", 20)

    best_name = "CPUExecutionProvider"
    best_prio = 20
    for prov, prio in _PROVIDER_PRIORITY.items():
        if prov in available and prio > best_prio:
            best_name = prov
            best_prio = prio
    return (best_name, best_prio)


def _download_model(url: str, dest: Path) -> None:
    """Download a model file with proper User-Agent header."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")

    req = urllib.request.Request(url, headers={"User-Agent": "YuAiManager/1.0"})
    logger.info("Downloading ONNX model: %s -> %s", url, dest)

    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        tmp.replace(dest)
        logger.info("ONNX model downloaded: %s", dest)
    except Exception:
        # Clean up partial download
        if tmp.exists():
            tmp.unlink()
        raise


@register_backend
class OnnxYoloBackend(YoloBackend):
    """ONNX Runtime YOLO backend (CUDA / ROCm / CPU)."""

    name = "onnx"

    def __init__(self) -> None:
        self._session = None
        self._model_name: str = ""
        self._input_size: int = 640

    @staticmethod
    def is_available() -> bool:
        """Check if onnxruntime is importable."""
        try:
            import onnxruntime  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def priority() -> int:
        _, prio = _get_best_provider()
        return prio

    @staticmethod
    def supported_models() -> list[str]:
        return list(ONNX_MODELS.keys())

    def load_model(self, model_name: str, input_size: int = 640) -> None:
        """Load an ONNX YOLO model, downloading if needed.

        Args:
            model_name: Key in ONNX_MODELS (e.g. "yolov8n").
            input_size: Model input dimension (overridden by model config).
        """
        import onnxruntime as ort

        if self._session is not None and self._model_name == model_name:
            return  # Already loaded

        info = ONNX_MODELS.get(model_name)
        if info is None:
            raise ValueError(
                f"Unknown ONNX model: {model_name}. "
                f"Supported: {list(ONNX_MODELS.keys())}"
            )

        self._input_size = info["input_size"]
        fname = info.get("filename", f"{model_name}.onnx")
        model_path = _CACHE_DIR / fname

        if not model_path.exists():
            _download_model(info["url"], model_path)

        # Create session with best available provider
        provider_name, _ = _get_best_provider()
        logger.info(
            "Creating ONNX session: model=%s, provider=%s",
            model_name, provider_name,
        )

        self._session = ort.InferenceSession(
            str(model_path),
            providers=[provider_name],
        )
        self._model_name = model_name
        try:
            from extensions.builtin_inference.core_impl.ort_provider import register_active_session
            register_active_session(f"yolo_detect_{model_name}", self._session, model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)

        logger.info(
            "ONNX YOLO model loaded: %s (%s)",
            model_name, provider_name,
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
        """Run YOLO detection via ONNX Runtime.

        Args:
            image: (H, W, 3) uint8 RGB, already letterbox-resized to input_size.
            scale_info: From yolo_preprocess.letterbox_resize.
            conf_threshold: Minimum confidence.
            iou_threshold: NMS IoU threshold.

        Returns:
            List of detection dicts (class_id, class_name, confidence, bbox).
        """
        if self._session is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        from . import postprocess_common

        # Preprocess: HWC uint8 -> NCHW float32 [0, 1]
        blob = image.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)

        # Run inference
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: blob})

        # YOLOv8/YOLO11 ONNX output: (1, 84, 8400)
        # 84 = 4 box coords (xywh) + 80 class scores
        raw = outputs[0]  # (1, 84, 8400)
        raw = raw[0]  # (84, 8400)
        raw = raw.T  # (8400, 84)

        boxes_xywh = raw[:, :4]  # (8400, 4) - already in pixel coords
        class_scores = raw[:, 4:]  # (8400, 80)

        return postprocess_common.build_detections(
            boxes_xywh,
            class_scores,
            conf_threshold,
            iou_threshold,
            scale_info=scale_info,
        )

    def detect_batch(
        self,
        images: list[np.ndarray],
        scale_infos: list[dict | None],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> list[list[dict]]:
        """Run YOLO detection on a batch via ONNX Runtime.

        Stacks images into a single (N, 3, H, W) tensor for
        GPU-efficient batch inference.
        """
        if self._session is None:
            raise RuntimeError("No model loaded. Call load_model() first.")
        if not images:
            return []

        from . import postprocess_common

        # Stack into (N, 3, H, W) float32
        blobs = []
        for img in images:
            b = img.astype(np.float32) / 255.0
            blobs.append(b.transpose(2, 0, 1))  # (3, H, W)
        batch = np.stack(blobs)  # (N, 3, H, W)

        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: batch})

        # Output: (N, 84, 8400)
        raw_batch = outputs[0]

        results = []
        for i in range(raw_batch.shape[0]):
            raw = raw_batch[i].T  # (8400, 84)
            boxes_xywh = raw[:, :4]
            class_scores = raw[:, 4:]
            si = scale_infos[i] if i < len(scale_infos) else None
            results.append(postprocess_common.build_detections(
                boxes_xywh, class_scores,
                conf_threshold, iou_threshold,
                scale_info=si,
            ))
        return results

    def close(self) -> None:
        """Release the ONNX session."""
        if self._session is not None:
            self._session = None
            logger.info("ONNX YOLO backend closed")
