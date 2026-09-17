"""Detector helpers backing InferenceProbe."""

from __future__ import annotations

import logging

from .probe_capabilities import (
    CLIP_HEF,
    CLIP_ONNX_CACHE,
    WHISPER_HEFS,
    YOLO_HEFS,
    InferenceCapability,
    tagger_cache_paths,
)
from .probe_http import get_llm_endpoints, http_get

logger = logging.getLogger(__name__)


def has_onnxruntime() -> bool:
    try:
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def onnx_device() -> str:
    try:
        import onnxruntime as ort

        available = ort.get_available_providers()
    except ImportError:
        return "onnx-cpu"

    provider_map = {
        "CUDAExecutionProvider": "onnx-cuda",
        "DirectMLExecutionProvider": "onnx-directml",
        "CoreMLExecutionProvider": "onnx-coreml",
        "ROCMExecutionProvider": "onnx-rocm",
        "TensorrtExecutionProvider": "onnx-tensorrt",
        "OpenVINOExecutionProvider": "onnx-openvino",
    }
    for provider, device in provider_map.items():
        if provider in available:
            return device
    return "onnx-cpu"


def has_faster_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def detect_clip(probe) -> list[InferenceCapability]:
    caps: list[InferenceCapability] = []
    hef_path = probe._hef_dir / CLIP_HEF
    if hef_path.exists():
        caps.append(
            InferenceCapability(
                inference_type="clip",
                backend="hailo",
                device="hailo-10h",
                model_name="clip_vit_b_16",
                ready=True,
            )
        )

    if probe._has_onnxruntime():
        model_exists = (CLIP_ONNX_CACHE / "model.onnx").exists()
        caps.append(
            InferenceCapability(
                inference_type="clip",
                backend="onnx",
                device=probe._onnx_device(),
                model_name="clip_vit_b_16",
                ready=True,
            )
        )
        if model_exists:
            logger.debug("CLIP ONNX model found at %s", CLIP_ONNX_CACHE)
    return caps


def detect_yolo(probe) -> list[InferenceCapability]:
    caps: list[InferenceCapability] = []
    for hef_name in YOLO_HEFS:
        hef_path = probe._hef_dir / hef_name
        if hef_path.exists():
            caps.append(
                InferenceCapability(
                    inference_type="yolo",
                    backend="hailo",
                    device="hailo-10h",
                    model_name=hef_name.replace(".hef", ""),
                    ready=True,
                )
            )
    if probe._has_onnxruntime():
        caps.append(
            InferenceCapability(
                inference_type="yolo",
                backend="onnx",
                device=probe._onnx_device(),
                model_name="yolov8n",
                ready=True,
            )
        )
    return caps


def detect_tagger(probe) -> list[InferenceCapability]:
    caps: list[InferenceCapability] = []
    for cache_dir in tagger_cache_paths():
        if not cache_dir.exists():
            continue
        for sub in sorted(cache_dir.iterdir()):
            if not sub.is_dir():
                continue
            onnx_model = sub / "model.onnx"
            hef_model = sub / "model.hef"
            if hef_model.exists():
                caps.append(
                    InferenceCapability(
                        inference_type="tagger",
                        backend="hailo",
                        device="hailo-10h",
                        model_name=sub.name,
                        ready=True,
                    )
                )
            if onnx_model.exists() and probe._has_onnxruntime():
                caps.append(
                    InferenceCapability(
                        inference_type="tagger",
                        backend="onnx",
                        device=probe._onnx_device(),
                        model_name=sub.name,
                        ready=True,
                    )
                )
    return caps


def detect_whisper(probe) -> list[InferenceCapability]:
    caps: list[InferenceCapability] = []
    for hef_name in WHISPER_HEFS:
        hef_path = probe._hef_dir / hef_name
        if hef_path.exists():
            caps.append(
                InferenceCapability(
                    inference_type="whisper",
                    backend="hailo",
                    device="hailo-10h",
                    model_name=hef_name.replace(".hef", "").lower().replace("-", "_"),
                    ready=True,
                )
            )
    if probe._has_faster_whisper():
        caps.append(
            InferenceCapability(
                inference_type="whisper",
                backend="onnx",
                device=probe._onnx_device(),
                model_name="faster_whisper",
                ready=True,
            )
        )
    return caps


def detect_llm(probe) -> list[InferenceCapability]:
    caps: list[InferenceCapability] = []
    endpoints = get_llm_endpoints()
    for _category, cfg in endpoints.items():
        base_url: str = cfg.get("base_url", "").rstrip("/")
        if not base_url:
            continue

        if ":11434" in base_url:
            backend = "ollama"
        elif ":1234" in base_url:
            backend = "lm-studio"
        else:
            backend = "openai-compat"

        resp = http_get(f"{base_url}/v1/models")
        ready = False
        model_name = ""
        if resp is not None and resp.status_code == 200:
            ready = True
            try:
                data = resp.json()
                items = data.get("models") or data.get("data") or []
                if items:
                    model_name = items[0].get("id", "")
            except Exception:
                logger.debug("Failed to parse /v1/models response from %s", base_url, exc_info=True)

        caps.append(
            InferenceCapability(
                inference_type="llm",
                backend=backend,
                device=base_url,
                model_name=model_name,
                ready=ready,
            )
        )
    return caps
