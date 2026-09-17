"""Hailo-10H Speech2Text inference wrapper (singleton).

Wraps ``hailo_platform.genai.Speech2Text`` with device_manager integration.
Input: PCM float32, mono, 16 kHz (little-endian).
"""

import logging
import threading
from typing import Optional

import numpy as np

from .model_download import get_hef_path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: Optional["HailoS2T"] = None


class HailoS2T:
    """Thin wrapper around ``hailo_platform.genai.Speech2Text``."""

    def __init__(self, model_name: str):
        from hailo_platform.genai import Speech2Text

        from core.hailo_device_core.device_manager import acquire_genai

        path = str(get_hef_path(model_name))
        self._s2t = acquire_genai(
            "s2t", path,
            lambda vd, p: Speech2Text(vd, p),
        )
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: str = "en",
        timeout_ms: int = 120000,
    ) -> str:
        """Transcribe audio to text (single string result)."""
        from hailo_platform.genai import Speech2TextTask

        segments = self._s2t.generate_all_segments(
            audio_data=_ensure_le_float32(audio_data),
            task=Speech2TextTask.TRANSCRIBE,
            language=language,
            timeout_ms=timeout_ms,
        )
        return "".join(seg.text for seg in segments).strip()

    def transcribe_segments(
        self,
        audio_data: np.ndarray,
        language: str = "en",
        timeout_ms: int = 120000,
    ) -> list[dict]:
        """Transcribe audio and return per-segment results."""
        from hailo_platform.genai import Speech2TextTask

        segments = self._s2t.generate_all_segments(
            audio_data=_ensure_le_float32(audio_data),
            task=Speech2TextTask.TRANSCRIBE,
            language=language,
            timeout_ms=timeout_ms,
        )
        return [
            {"text": seg.text, "start": seg.start_sec, "end": seg.end_sec}
            for seg in segments
        ]

    def close(self) -> None:
        from core.hailo_device_core.device_manager import release_device
        release_device("s2t")


def _ensure_le_float32(audio: np.ndarray) -> np.ndarray:
    """Convert audio to little-endian float32 normalised to [-1, 1]."""
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    return audio.astype("<f4")


def get_s2t(model_name: str = "whisper-base") -> HailoS2T:
    """Return the singleton HailoS2T, loading *model_name* if needed."""
    from core.hailo_device_core.device_manager import is_model_active

    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            # Verify device_manager still holds this model; discard stale wrappers.
            if is_model_active("s2t"):
                return _instance
            # Evicted externally — discard stale singleton
            logger.info("S2T singleton was evicted externally; reloading")
            _instance = None
        if _instance is not None:
            _instance.close()
            _instance = None
        _instance = HailoS2T(model_name)
        return _instance


def close_s2t() -> None:
    """Release the singleton S2T."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
            _instance = None
