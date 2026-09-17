"""faster-whisper backend for Speech-to-Text (CUDA / CPU).

Uses CTranslate2 via faster-whisper. Automatically selects CUDA if available.
"""

import logging

import numpy as np

from .base import S2TBackend

logger = logging.getLogger(__name__)

# faster-whisper model ID mapping
_MODEL_MAP = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
}


class FasterWhisperBackend(S2TBackend):
    """faster-whisper backend (CUDA or CPU)."""

    name = "faster-whisper"

    def __init__(self):
        self._model = None
        self._model_size = ""
        self._device = "cpu"
        self._compute_type = "int8"

    @staticmethod
    def is_available() -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def priority() -> int:
        return 50

    def load_model(self, model_size: str) -> None:
        if self._model is not None and self._model_size == model_size:
            return
        self.close()

        from faster_whisper import WhisperModel

        self._device, self._compute_type = _detect_device()
        model_id = _MODEL_MAP.get(model_size, "base")

        logger.info(
            "Loading faster-whisper '%s' on %s (%s)",
            model_id, self._device, self._compute_type,
        )
        self._model = WhisperModel(
            model_id,
            device=self._device,
            compute_type=self._compute_type,
        )
        self._model_size = model_size
        self.name = f"faster-whisper-{self._device}"
        logger.info("faster-whisper backend ready: %s on %s", model_id, self._device)

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: str = "en",
    ) -> list[dict]:
        if self._model is None:
            raise RuntimeError("Model not loaded")

        audio = _to_float32(audio_data)
        segments_iter, _info = self._model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        result = []
        for seg in segments_iter:
            result.append({
                "text": seg.text.strip(),
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
            })
        return result

    def transcribe_raw(
        self,
        audio: "np.ndarray",
        language: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        **kwargs,
    ):
        """Expose the raw faster-whisper transcribe() iterator for live streaming.

        Returns (segments_iterator, info) directly from the underlying model.
        Avoids callers accessing the private ``_model`` attribute.
        """
        return self._model.transcribe(
            audio,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            **kwargs,
        )

    def close(self) -> None:
        self._model = None
        self._model_size = ""

    @staticmethod
    def cached_models() -> list:
        """Detect locally cached faster-whisper (CTranslate2) models."""
        return _detect_cached_fw_models()

    def info(self) -> dict:
        base = super().info()
        base["device"] = self._device
        base["compute_type"] = self._compute_type
        return base


def _detect_device() -> tuple:
    """Detect best device: CUDA > CPU. Returns (device, compute_type).

    Performs a runtime CUDA test to catch missing DLLs (cublas, cudnn etc.)
    that pass the initial detection but fail at execution time.
    """
    try:
        import torch
        if torch.cuda.is_available():
            # Runtime test: actually run a small op on the GPU
            try:
                _t = torch.zeros(1, device="cuda")
                del _t
                logger.info("CUDA detected: %s", torch.cuda.get_device_name(0))
                return "cuda", "float16"
            except RuntimeError as e:
                logger.warning("CUDA detected but runtime test failed: %s", e)
    except ImportError:
        pass

    # CTranslate2 may have CUDA support without torch
    try:
        import ctranslate2
        cuda_types = ctranslate2.get_supported_compute_types("cuda")
        if cuda_types:
            # Runtime test: try to create a tiny model storage on CUDA
            try:
                sr = ctranslate2.StorageView.from_array(
                    [0.0], dtype="float32", device="cuda"
                )
                del sr
                ct = "float16" if "float16" in cuda_types else "int8"
                logger.info("CUDA detected via ctranslate2 (compute=%s)", ct)
                return "cuda", ct
            except Exception as e:
                logger.warning("CUDA ctranslate2 runtime test failed: %s", e)
    except Exception:
        logger.info("ctranslate2 CUDA support unavailable", exc_info=True)

    logger.info("Using CPU for faster-whisper")
    return "cpu", "int8"


def _detect_cached_fw_models() -> list:
    """Check HuggingFace cache for downloaded faster-whisper models."""
    from pathlib import Path

    results = []
    # faster-whisper stores models in HF Hub cache
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    if not hf_cache.is_dir():
        return results

    for size in ("tiny", "base", "small", "medium", "large-v3"):
        # CTranslate2 model dirs: models--Systran--faster-whisper-{size}
        # or models--guillaumekln--faster-whisper-{size} (legacy)
        for prefix in ("Systran", "guillaumekln"):
            model_dir = hf_cache / f"models--{prefix}--faster-whisper-{size}"
            if model_dir.is_dir():
                # Check if model.bin exists in any snapshot
                snapshots = model_dir / "snapshots"
                if snapshots.is_dir():
                    for snap in snapshots.iterdir():
                        model_bin = snap / "model.bin"
                        if model_bin.is_file():
                            total = sum(
                                f.stat().st_size
                                for f in snap.rglob("*")
                                if f.is_file()
                            )
                            results.append({
                                "size": size,
                                "path": str(snap),
                                "size_bytes": total,
                            })
                            break
                break  # No need to check duplicates of same size
    # Also check bare model names (faster-whisper downloads "base" etc directly)
    # These end up as models--Systran--faster-whisper-base or similar
    return results


def _to_float32(audio: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 [-1, 1]."""
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    if audio.dtype != np.float32:
        return audio.astype(np.float32)
    return audio
