"""InferenceProbe facade."""

from __future__ import annotations

import logging
from pathlib import Path

from .probe_capabilities import DEFAULT_HEF_DIR, InferenceCapability
from .probe_detectors import (
    detect_clip,
    detect_llm,
    detect_tagger,
    detect_whisper,
    detect_yolo,
    has_faster_whisper,
    has_onnxruntime,
    onnx_device,
)

logger = logging.getLogger(__name__)


class InferenceProbe:
    """Detect available inference backends and models on the local system."""

    def __init__(self, hef_dir: str | None = None):
        self._hef_dir = Path(hef_dir) if hef_dir else Path(DEFAULT_HEF_DIR)

    def detect_all(self) -> list[InferenceCapability]:
        caps: list[InferenceCapability] = []
        for detector in (
            self._detect_clip,
            self._detect_yolo,
            self._detect_tagger,
            self._detect_whisper,
            self._detect_llm,
        ):
            try:
                caps.extend(detector())
            except Exception:
                logger.debug("Detector %s failed", detector.__name__, exc_info=True)
        return caps

    def detect_types(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for cap in self.detect_all():
            if cap.ready and cap.inference_type not in seen:
                seen.add(cap.inference_type)
                result.append(cap.inference_type)
        return result

    def _detect_clip(self) -> list[InferenceCapability]:
        return detect_clip(self)

    def _detect_yolo(self) -> list[InferenceCapability]:
        return detect_yolo(self)

    def _detect_tagger(self) -> list[InferenceCapability]:
        return detect_tagger(self)

    def _detect_whisper(self) -> list[InferenceCapability]:
        return detect_whisper(self)

    def _detect_llm(self) -> list[InferenceCapability]:
        return detect_llm(self)

    @staticmethod
    def _has_onnxruntime() -> bool:
        return has_onnxruntime()

    @staticmethod
    def _onnx_device() -> str:
        return onnx_device()

    @staticmethod
    def _has_faster_whisper() -> bool:
        return has_faster_whisper()


__all__ = ["InferenceCapability", "InferenceProbe"]
