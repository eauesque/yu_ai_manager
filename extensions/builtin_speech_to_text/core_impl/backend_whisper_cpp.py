"""whisper.cpp backend for Speech-to-Text (CPU, lightweight).

Uses pywhispercpp as the lightest-weight CPU fallback.
No PyTorch dependency required.
"""

import logging
from pathlib import Path

import numpy as np

from .base import S2TBackend

logger = logging.getLogger(__name__)

_GGML_MODELS_DIR = Path.home() / ".cache" / "whisper-cpp"


class WhisperCppBackend(S2TBackend):
    """whisper.cpp backend (CPU only, minimal dependencies)."""

    name = "whisper-cpp"

    def __init__(self):
        self._whisper = None
        self._model_size = ""

    @staticmethod
    def is_available() -> bool:
        try:
            from pywhispercpp.model import Model  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def priority() -> int:
        return 10

    def load_model(self, model_size: str) -> None:
        if self._whisper is not None and self._model_size == model_size:
            return
        self.close()

        from pywhispercpp.model import Model

        _GGML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Loading whisper.cpp model: %s", model_size)

        self._whisper = Model(
            model_size,
            models_dir=str(_GGML_MODELS_DIR),
            print_progress=False,
            print_realtime=False,
        )
        self._model_size = model_size
        logger.info("whisper.cpp backend ready: %s", model_size)

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: str = "en",
    ) -> list[dict]:
        if self._whisper is None:
            raise RuntimeError("Model not loaded")

        audio = _to_float32(audio_data)
        segments = self._whisper.transcribe(
            audio,
            language=language,
        )
        result = []
        for seg in segments:
            result.append({
                "text": seg.text.strip(),
                "start": round(seg.t0 / 100.0, 3),
                "end": round(seg.t1 / 100.0, 3),
            })
        return result

    @staticmethod
    def cached_models() -> list:
        """Detect locally cached whisper.cpp GGML models."""
        results = []
        if not _GGML_MODELS_DIR.is_dir():
            return results
        for size in ("tiny", "base", "small", "medium", "large"):
            for pattern in (f"ggml-{size}.bin", f"ggml-model-whisper-{size}.bin"):
                model_file = _GGML_MODELS_DIR / pattern
                if model_file.is_file():
                    results.append({
                        "size": size,
                        "path": str(model_file),
                        "size_bytes": model_file.stat().st_size,
                    })
                    break
        return results

    def close(self) -> None:
        self._whisper = None
        self._model_size = ""


def _to_float32(audio: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 [-1, 1]."""
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    if audio.dtype != np.float32:
        return audio.astype(np.float32)
    return audio
