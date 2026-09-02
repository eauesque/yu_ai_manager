"""Shared inference capability data structures and cache paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HEF_DIR = os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models"))
CLIP_ONNX_CACHE = Path.home() / ".cache" / "yu_ai_manager" / "clip_onnx"
YOLO_ONNX_CACHE = Path.home() / ".cache" / "yu_ai_manager" / "yolo_onnx"
WHISPER_ONNX_CACHE = Path.home() / ".cache" / "yu_ai_manager" / "whisper_onnx"
CLIP_HEF = "clip_vit_b_16_image_encoder.hef"
YOLO_HEFS = ("yolov8n.hef", "yolov11n.hef", "yolov5m_wo_spp.hef")
WHISPER_HEFS = ("Whisper-Base.hef", "Whisper-Small.hef")


def tagger_cache_paths() -> list[Path]:
    from core.paths import cache_path

    return [
        Path.home() / ".cache" / "yu_ai_manager" / "wd_tagger",
        cache_path("wd_tagger"),
    ]


@dataclass
class InferenceCapability:
    inference_type: str
    backend: str
    device: str
    model_name: str
    ready: bool

    def to_dict(self) -> dict:
        return {
            "inference_type": self.inference_type,
            "backend": self.backend,
            "device": self.device,
            "model_name": self.model_name,
            "ready": self.ready,
        }
