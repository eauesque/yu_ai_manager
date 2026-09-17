"""CLIP image encoder factory with automatic backend selection.

Priority order: Hailo-10H > CoreML (macOS only) > ONNX > (none).
Falls back gracefully when hardware or dependencies are missing.
"""

import logging
from collections.abc import Callable

from .encoder_abc import ClipImageEncoder

logger = logging.getLogger(__name__)


def _try_hailo() -> ClipImageEncoder | None:
    """Attempt to get the Hailo encoder (returns None if unavailable)."""
    try:
        from importlib import import_module
        _hailo_inf = import_module("extensions.builtin_hailo_semantic_search.core_impl.hailo_inference")
        get_encoder = _hailo_inf.get_encoder
        is_hailo_available = _hailo_inf.is_hailo_available
        if is_hailo_available():
            return get_encoder()
    except Exception as exc:
        logger.debug("Hailo backend not available: %s", exc)
    return None


def _try_coreml() -> ClipImageEncoder | None:
    """Attempt to get the CoreML encoder (returns None if unavailable)."""
    try:
        from core.clip_coreml_core.coreml_encoder import get_encoder, is_coreml_available
        if is_coreml_available():
            return get_encoder()
    except Exception as exc:
        logger.debug("CoreML backend not available: %s", exc)
    return None


def _try_onnx() -> ClipImageEncoder | None:
    """Attempt to get the ONNX encoder (returns None if unavailable)."""
    try:
        from core.clip_onnx_core.onnx_encoder import get_encoder, is_onnx_available
        if is_onnx_available():
            return get_encoder()
    except Exception as exc:
        logger.debug("ONNX backend not available: %s", exc)
    return None


def get_best_encoder(preferred: str = "auto") -> ClipImageEncoder:
    """Get the best available CLIP image encoder.

    Args:
        preferred: "auto" (default priority), "hailo", "coreml", or "onnx".

    Returns:
        A ClipImageEncoder instance.

    Raises:
        RuntimeError: if no encoder backend is available.
    """
    if preferred == "hailo":
        enc = _try_hailo()
        if enc:
            return enc
        raise RuntimeError("Hailo backend requested but not available")

    if preferred == "coreml":
        enc = _try_coreml()
        if enc:
            return enc
        raise RuntimeError("CoreML backend requested but not available")

    if preferred == "onnx":
        enc = _try_onnx()
        if enc:
            return enc
        raise RuntimeError("ONNX backend requested but not available")

    # Auto: try in priority order (Hailo > CoreML > ONNX)
    enc = _try_hailo()
    if enc:
        logger.info("Using Hailo-10H CLIP encoder")
        return enc

    enc = _try_coreml()
    if enc:
        logger.info("Using Core ML CLIP encoder (ANE)")
        return enc

    enc = _try_onnx()
    if enc:
        logger.info("Using ONNX CLIP encoder (%s)", enc.backend_name)
        return enc

    raise RuntimeError(
        "No CLIP encoder backend available. "
        "Install onnxruntime and download the CLIP ONNX model, "
        "or connect a Hailo-10H device."
    )


def get_preprocessor(encoder: ClipImageEncoder) -> Callable:
    """Return the appropriate preprocessing function for the encoder.

    Args:
        encoder: A ClipImageEncoder instance.

    Returns:
        A callable(path) -> preprocessed numpy array.
    """
    name = encoder.backend_name
    if name == "hailo-10h":
        from importlib import import_module
        _hailo_pp = import_module("extensions.builtin_hailo_semantic_search.core_impl.image_preprocess")
        return _hailo_pp.preprocess_image
    elif name.startswith("coreml"):
        from core.clip_coreml_core.preprocess import preprocess_image
        return preprocess_image
    elif name.startswith("onnx"):
        from core.clip_onnx_core.preprocess import preprocess_image
        return preprocess_image
    else:
        raise ValueError(f"Unknown encoder backend: {name}")


def get_encoder_info() -> dict:
    """Return info about all available encoder backends (for API/UI)."""
    backends = []

    # Hailo
    hailo_entry: dict = {"name": "hailo-10h", "available": False, "priority": 1}
    try:
        from importlib import import_module
        _hailo_inf = import_module("extensions.builtin_hailo_semantic_search.core_impl.hailo_inference")
        status = _hailo_inf.get_hailo_status()
        hailo_entry["available"] = status["available"]
        hailo_entry["status"] = status
    except Exception as exc:
        hailo_entry["status"] = {
            "available": False,
            "runtime_ok": False,
            "hardware_ok": False,
            "hef_ok": False,
            "reason": f"hailo backend import failed: {exc}",
        }
    backends.append(hailo_entry)

    # CoreML (macOS only)
    try:
        from core.clip_coreml_core.coreml_encoder import is_coreml_available
        coreml_ok = is_coreml_available()
    except Exception:
        coreml_ok = False
    backends.append({
        "name": "coreml-ane",
        "available": coreml_ok,
        "priority": 2,
    })

    # ONNX
    try:
        from core.clip_onnx_core.onnx_encoder import is_onnx_available
        onnx_ok = is_onnx_available()
    except Exception:
        onnx_ok = False

    onnx_info: dict = {"name": "onnx", "available": onnx_ok, "priority": 3}
    try:
        from core.clip_onnx_core.model_download import get_model_status
        onnx_info["model_status"] = get_model_status()
    except Exception:
        logger.warning("ONNX model status was unreadable", exc_info=True)
    backends.append(onnx_info)

    return {
        "backends": backends,
        "any_available": any(b["available"] for b in backends),
    }


def is_any_encoder_available() -> bool:
    """Check if at least one CLIP encoder backend is available."""
    try:
        info = get_encoder_info()
        return info["any_available"]
    except Exception:
        return False
