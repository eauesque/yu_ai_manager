"""Inference engines for ONNX Runtime and Hailo-10H NPU backends."""

from __future__ import annotations

import abc
from pathlib import Path

from .preprocess import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    build_tag_list,
    preprocess_image_bytes,
)


class InferenceEngine(abc.ABC):
    """Abstract inference backend."""

    @abc.abstractmethod
    def predict(self, image_data: bytes) -> list[dict]:
        """Run inference on raw image bytes. Returns tag list."""

    @abc.abstractmethod
    def get_device_info(self) -> str:
        """Return device identifier for /health."""

    @abc.abstractmethod
    def get_backend_name(self) -> str:
        """Return backend name string."""


class OnnxEngine(InferenceEngine):
    """ONNX Runtime inference backend."""

    def __init__(
        self,
        logger,
        model_dir: Path,
        tag_names: list[str],
        categories: list[str],
        general_threshold: float = DEFAULT_GENERAL_THRESHOLD,
        character_threshold: float = DEFAULT_CHARACTER_THRESHOLD,
        provider: str = "",
    ):
        self._tag_names = tag_names
        self._categories = categories
        self._general_threshold = general_threshold
        self._character_threshold = character_threshold

        import onnxruntime as ort

        model_path = model_dir / "model.onnx"
        if not model_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {model_path}")

        providers = self.select_providers(provider)
        logger.info("Loading ONNX model: %s (providers: %s)", model_path, providers)
        self._session = ort.InferenceSession(str(model_path), providers=providers)
        active = self._session.get_providers()
        logger.info("Active ORT providers: %s", active)
        self._input_name = self._session.get_inputs()[0].name
        self._active_provider = active[0] if active else "unknown"
        try:
            from extensions.builtin_inference.core_impl.ort_provider import register_active_session
            register_active_session("lan_cowork_inference", self._session, model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)

    @staticmethod
    def select_providers(preferred: str = "") -> list[str]:
        """Select execution providers in priority order.

        Used by clip.py and yolo.py as well, so this is a public method.
        """
        import onnxruntime as ort

        available = ort.get_available_providers()
        priority = [
            "TensorrtExecutionProvider",
            "CUDAExecutionProvider",
            "ROCMExecutionProvider",
            "MIGraphXExecutionProvider",
            "DirectMLExecutionProvider",
            "OpenVINOExecutionProvider",
            "QNNExecutionProvider",
            "CoreMLExecutionProvider",
            "AzureExecutionProvider",
            "CPUExecutionProvider",
        ]
        if preferred:
            name_map = {
                "tensorrt": "TensorrtExecutionProvider",
                "cuda": "CUDAExecutionProvider",
                "rocm": "ROCMExecutionProvider",
                "migraphx": "MIGraphXExecutionProvider",
                "directml": "DirectMLExecutionProvider",
                "openvino": "OpenVINOExecutionProvider",
                "qnn": "QNNExecutionProvider",
                "coreml": "CoreMLExecutionProvider",
                "azure": "AzureExecutionProvider",
                "cpu": "CPUExecutionProvider",
            }
            full = name_map.get(preferred.lower(), preferred)
            if full in available:
                return [full, "CPUExecutionProvider"]
        result = [provider for provider in priority if provider in available]
        return result if result else ["CPUExecutionProvider"]

    def predict(self, image_data: bytes) -> list[dict]:
        probs = self._session.run(
            None, {self._input_name: preprocess_image_bytes(image_data)}
        )[0][0]
        return build_tag_list(
            probs,
            self._tag_names,
            self._categories,
            self._general_threshold,
            self._character_threshold,
        )

    def get_device_info(self) -> str:
        provider = self._active_provider.lower()
        provider_map = {
            "tensorrt": "onnx-tensorrt",
            "cuda": "onnx-cuda",
            "rocm": "onnx-rocm",
            "migraphx": "onnx-migraphx",
            "directml": "onnx-directml",
            "openvino": "onnx-openvino",
            "qnn": "onnx-qnn",
            "coreml": "onnx-coreml",
            "azure": "onnx-azure",
        }
        for key, value in provider_map.items():
            if key in provider:
                return value
        return "onnx-cpu"

    def get_backend_name(self) -> str:
        return "onnx"

    @staticmethod
    def is_available() -> bool:
        try:
            import onnxruntime  # noqa: F401

            return True
        except ImportError:
            return False


class HailoEngine(InferenceEngine):
    """Hailo-10H NPU inference backend via shared device manager."""

    _OWNER = "lan-tagger"

    def __init__(
        self,
        logger,
        model_dir: Path,
        tag_names: list[str],
        categories: list[str],
        general_threshold: float = DEFAULT_GENERAL_THRESHOLD,
        character_threshold: float = DEFAULT_CHARACTER_THRESHOLD,
    ):
        self._tag_names = tag_names
        self._categories = categories
        self._general_threshold = general_threshold
        self._character_threshold = character_threshold

        from core.hailo_device_core.device_manager import acquire_device

        hef_path = model_dir / "model.hef"
        if not hef_path.exists():
            raise FileNotFoundError(f"HEF model not found: {hef_path}")

        self._hef_path = str(hef_path)
        logger.info("Loading HEF model: %s", hef_path)
        infer_model, _configured, quant_params_list = acquire_device(
            self._OWNER, self._hef_path,
        )
        self._input_shape = infer_model.input().shape
        self._output_shape = infer_model.output().shape
        qp = quant_params_list[0] if quant_params_list else None
        self._qp_scale = qp["scale"] if qp else 1.0
        self._qp_zp = qp["zero_point"] if qp else 0.0
        logger.info(
            "Hailo engine ready -- input: %s, output: %s",
            self._input_shape,
            self._output_shape,
        )

    def _dequantize(self, raw_output):
        import numpy as np

        data = np.array(raw_output, dtype=np.float32)
        data = (data - self._qp_zp) * self._qp_scale
        return 1.0 / (1.0 + np.exp(-data))

    def predict(self, image_data: bytes) -> list[dict]:
        import numpy as np

        from core.hailo_device_core.device_manager import acquire_device

        _infer_model, configured, _ = acquire_device(
            self._OWNER, self._hef_path,
        )

        input_u8 = np.clip(preprocess_image_bytes(image_data), 0, 255).astype(
            np.uint8
        )
        bindings = configured.create_bindings()
        bindings.input().set_buffer(input_u8)

        output_size = 1
        for dim in self._output_shape:
            output_size *= dim
        output_buffer = np.empty(output_size, dtype=np.uint8)
        bindings.output().set_buffer(output_buffer)
        configured.run([bindings])

        probs = self._dequantize(output_buffer)
        return build_tag_list(
            probs,
            self._tag_names,
            self._categories,
            self._general_threshold,
            self._character_threshold,
        )

    def get_device_info(self) -> str:
        return "hailo-10h"

    def get_backend_name(self) -> str:
        return "hailo"

    @staticmethod
    def is_available() -> bool:
        try:
            from core.hailo_device_core.device_manager import is_hailo_available
            return is_hailo_available()
        except Exception:
            return False


def create_engine(
    logger,
    backend: str,
    model_dir: Path,
    tag_names: list[str],
    categories: list[str],
    general_threshold: float = DEFAULT_GENERAL_THRESHOLD,
    character_threshold: float = DEFAULT_CHARACTER_THRESHOLD,
    ort_provider: str = "",
) -> InferenceEngine:
    """Create inference engine based on backend selection."""
    kwargs = {
        "logger": logger,
        "model_dir": model_dir,
        "tag_names": tag_names,
        "categories": categories,
        "general_threshold": general_threshold,
        "character_threshold": character_threshold,
    }
    if backend == "hailo":
        return HailoEngine(**kwargs)
    if backend == "onnx":
        return OnnxEngine(**kwargs, provider=ort_provider)
    if backend != "auto":
        raise ValueError(
            f"Unknown backend: {backend!r}. Use 'onnx', 'hailo', or 'auto'."
        )
    # Auto-detect: try Hailo first, then ONNX
    hef_path = model_dir / "model.hef"
    if hef_path.exists():
        try:
            logger.info("Auto: trying Hailo backend...")
            return HailoEngine(**kwargs)
        except Exception as exc:
            logger.warning(
                "Hailo backend failed: %s -- falling back to ONNX", exc
            )

    onnx_path = model_dir / "model.onnx"
    if onnx_path.exists():
        try:
            logger.info("Auto: trying ONNX backend...")
            return OnnxEngine(**kwargs, provider=ort_provider)
        except Exception as exc:
            raise RuntimeError(
                f"No available backend. Hailo HEF not found or failed, "
                f"ONNX failed: {exc}"
            ) from exc

    raise RuntimeError(
        f"No model files found in {model_dir}. "
        f"Need model.hef (Hailo) or model.onnx (ONNX)."
    )
