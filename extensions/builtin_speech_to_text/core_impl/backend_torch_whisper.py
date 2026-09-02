"""PyTorch Whisper backend for Speech-to-Text (ROCm / CUDA / CPU).

Uses HuggingFace transformers pipeline. Primary target is AMD ROCm GPU,
but also works as a CUDA or CPU fallback when faster-whisper is unavailable.

ROCm detection: PyTorch exposes ROCm as CUDA via HIP,
distinguished by ``torch.version.hip`` being non-None.
"""

import contextlib
import logging

import numpy as np

from .base import S2TBackend

logger = logging.getLogger(__name__)

_HF_MODEL_MAP = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
}


class TorchWhisperBackend(S2TBackend):
    """PyTorch + transformers Whisper backend (ROCm / CUDA / CPU)."""

    name = "torch-whisper"

    def __init__(self):
        self._pipe = None
        self._model_size = ""
        self._device = "cpu"
        self._accel = "cpu"  # "rocm", "cuda", or "cpu"

    @staticmethod
    def is_available() -> bool:
        # Use find_spec to avoid importing torch/transformers at detection time.
        import importlib.util
        try:
            return (
                importlib.util.find_spec("torch") is not None
                and importlib.util.find_spec("transformers") is not None
            )
        except Exception:
            return False

    @staticmethod
    def priority() -> int:
        # Do NOT import torch here. torch import takes 10-30s on first call
        # and holds the GIL, which starves HailoRT inference threads and
        # triggers the faulthandler watchdog (_HAILO_CALL_TIMEOUT).
        # Use find_spec for a fast, non-blocking existence check only.
        # GPU-type detection (ROCm=70, CUDA=40) is deferred to load_model().
        import importlib.util
        if importlib.util.find_spec("torch") is None:
            return 20
        return 20  # CPU fallback; GPU priority refined at load_model() time

    def load_model(self, model_size: str) -> None:
        if self._pipe is not None and self._model_size == model_size:
            return
        self.close()

        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        model_id = _HF_MODEL_MAP.get(model_size, _HF_MODEL_MAP["base"])
        self._device, self._accel = _detect_device()
        torch_dtype = torch.float16 if self._device != "cpu" else torch.float32

        logger.info(
            "Loading %s on %s (%s, dtype=%s)",
            model_id, self._device, self._accel, torch_dtype,
        )

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
        model.to(self._device)

        processor = AutoProcessor.from_pretrained(model_id)

        self._pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=self._device,
        )
        self._model_size = model_size
        self.name = f"torch-whisper-{self._accel}"
        logger.info(
            "torch-whisper backend ready: %s on %s (%s)",
            model_size, self._device, self._accel,
        )

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: str = "en",
    ) -> list[dict]:
        if self._pipe is None:
            raise RuntimeError("Model not loaded")

        audio = _to_float32(audio_data)

        result = self._pipe(
            audio,
            return_timestamps=True,
            generate_kwargs={
                "language": language,
                "task": "transcribe",
            },
        )

        segments = []
        for chunk in result.get("chunks", []):
            ts = chunk.get("timestamp", (0.0, 0.0))
            start = ts[0] if ts[0] is not None else 0.0
            end = ts[1] if ts[1] is not None else start
            segments.append({
                "text": chunk.get("text", "").strip(),
                "start": round(start, 3),
                "end": round(end, 3),
            })

        # If chunks is empty, return entire text as 1 segment
        if not segments and result.get("text"):
            segments.append({
                "text": result["text"].strip(),
                "start": 0.0,
                "end": 0.0,
            })

        return segments

    def close(self) -> None:
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            self._model_size = ""
            # Release GPU memory
            # A probe: no CUDA, nothing to empty.
            with contextlib.suppress(Exception):
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    @staticmethod
    def cached_models() -> list:
        """Detect locally cached HuggingFace Whisper models."""
        from pathlib import Path

        results = []
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if not hf_cache.is_dir():
            return results

        for size, model_id in _HF_MODEL_MAP.items():
            # HF cache: models--openai--whisper-{size}
            safe_id = model_id.replace("/", "--")
            model_dir = hf_cache / f"models--{safe_id}"
            if model_dir.is_dir():
                snapshots = model_dir / "snapshots"
                if snapshots.is_dir():
                    for snap in snapshots.iterdir():
                        if snap.is_dir() and any(snap.iterdir()):
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
        return results

    def info(self) -> dict:
        base = super().info()
        base["device"] = self._device
        base["accelerator"] = self._accel
        return base


def _is_rocm() -> bool:
    """Check if PyTorch is built with ROCm (HIP)."""
    try:
        import torch
        return (
            hasattr(torch.version, "hip")
            and torch.version.hip is not None
            and torch.cuda.is_available()
        )
    except ImportError:
        return False


def _detect_device() -> tuple:
    """Detect best device. Returns (torch_device, accel_label).

    ROCm appears as 'cuda' in PyTorch but is identified by torch.version.hip.
    """
    try:
        import torch
        if torch.cuda.is_available():
            if _is_rocm():
                gpu_name = torch.cuda.get_device_name(0)
                logger.info("ROCm GPU detected: %s (HIP %s)", gpu_name, torch.version.hip)
                return "cuda", "rocm"
            else:
                gpu_name = torch.cuda.get_device_name(0)
                logger.info("CUDA GPU detected: %s", gpu_name)
                return "cuda", "cuda"
    except ImportError:
        pass
    return "cpu", "cpu"


def _to_float32(audio: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 [-1, 1]."""
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    if audio.dtype != np.float32:
        return audio.astype(np.float32)
    return audio
