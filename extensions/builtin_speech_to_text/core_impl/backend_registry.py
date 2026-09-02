"""Backend auto-detection and singleton management."""

import contextlib
import logging
import threading

from .backend_faster_whisper import FasterWhisperBackend
from .backend_hailo import HailoS2TBackend
from .backend_torch_whisper import TorchWhisperBackend
from .backend_whisper_cpp import WhisperCppBackend
from .base import S2TBackend

logger = logging.getLogger(__name__)

_ALL_BACKENDS = [
    HailoS2TBackend,
    FasterWhisperBackend,
    TorchWhisperBackend,
    WhisperCppBackend,
]

_lock = threading.Lock()
_instance: S2TBackend | None = None
_current_model_size = ""


def detect_available_backends() -> list:
    """Return list of available backend info dicts, sorted by priority."""
    result = []
    for cls in sorted(_ALL_BACKENDS, key=lambda c: c.priority(), reverse=True):
        available = False
        with contextlib.suppress(Exception):
            available = cls.is_available()
        cached = []
        with contextlib.suppress(Exception):
            cached = cls.cached_models()
        result.append({
            "name": cls.name if hasattr(cls, "name") else cls.__name__,
            "priority": cls.priority(),
            "available": available,
            "cached_models": cached,
        })
    return result


def get_backend(
    backend_pref: str = "auto",
    model_size: str = "base",
) -> S2TBackend:
    """Return singleton S2T backend, loading model if needed.

    Args:
        backend_pref: "auto", "hailo", "cuda", or "cpu".
        model_size: Whisper model size (tiny/base/small/medium).
    """
    global _instance, _current_model_size

    with _lock:
        if (_instance is not None
                and _current_model_size == model_size
                and _matches_pref(_instance, backend_pref)):
            return _instance

        # Close previous
        if _instance is not None:
            with contextlib.suppress(Exception):
                _instance.close()
            _instance = None
            _current_model_size = ""

        backend = _select_backend(backend_pref)
        backend.load_model(model_size)
        _instance = backend
        _current_model_size = model_size
        logger.info(
            "S2T backend active: %s (model=%s)",
            backend.name, model_size,
        )
        return backend


def close_backend() -> None:
    """Release the active backend."""
    global _instance, _current_model_size
    with _lock:
        if _instance is not None:
            with contextlib.suppress(Exception):
                _instance.close()
            _instance = None
            _current_model_size = ""


def get_active_info() -> dict | None:
    """Return info about the currently active backend, or None."""
    with _lock:
        if _instance is not None:
            return _instance.info()
    return None


def _select_backend(pref: str) -> S2TBackend:
    """Select a backend based on preference string."""
    if pref == "auto":
        return _auto_detect()

    mapping = {
        "hailo": HailoS2TBackend,
        "cuda": FasterWhisperBackend,
        "rocm": _pick_rocm_backend,
        "cpu": _pick_cpu_backend,
    }
    factory = mapping.get(pref)
    if factory is None:
        logger.warning("Unknown backend '%s', falling back to auto", pref)
        return _auto_detect()

    if callable(factory) and not isinstance(factory, type):
        return factory()

    if not factory.is_available():
        logger.warning(
            "Requested backend '%s' not available, falling back to auto", pref,
        )
        return _auto_detect()
    return factory()


def _auto_detect() -> S2TBackend:
    """Pick the best available backend by priority."""
    for cls in sorted(_ALL_BACKENDS, key=lambda c: c.priority(), reverse=True):
        try:
            if cls.is_available():
                logger.info("Auto-detected backend: %s", cls.name)
                return cls()
        except Exception as exc:
            logger.debug("Backend %s check failed: %s", cls.name, exc)
    raise RuntimeError(
        "No S2T backend available. Install faster-whisper or pywhispercpp."
    )


def _pick_rocm_backend() -> S2TBackend:
    """Pick ROCm backend (torch-whisper with HIP)."""
    if TorchWhisperBackend.is_available():
        from .backend_torch_whisper import _is_rocm
        if _is_rocm():
            return TorchWhisperBackend()
        raise RuntimeError("ROCm not detected. Ensure PyTorch is built with ROCm/HIP.")
    raise RuntimeError(
        "torch-whisper backend not available. Install torch and transformers."
    )


def _pick_cpu_backend() -> S2TBackend:
    """Pick the best CPU-only backend."""
    if FasterWhisperBackend.is_available():
        return FasterWhisperBackend()
    if WhisperCppBackend.is_available():
        return WhisperCppBackend()
    raise RuntimeError(
        "No CPU S2T backend available. Install faster-whisper or pywhispercpp."
    )


def _matches_pref(backend: S2TBackend, pref: str) -> bool:
    """Check if current backend matches the requested preference."""
    if pref == "auto":
        return True
    if pref == "hailo":
        return isinstance(backend, HailoS2TBackend)
    if pref == "cuda":
        return (isinstance(backend, FasterWhisperBackend)
                and backend._device == "cuda")
    if pref == "rocm":
        return (isinstance(backend, TorchWhisperBackend)
                and backend._accel == "rocm")
    if pref == "cpu":
        return not (isinstance(backend, HailoS2TBackend)
                    or (isinstance(backend, TorchWhisperBackend)
                        and backend._accel != "cpu"))
    return True
