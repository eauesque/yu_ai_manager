"""YOLO backend registry — manages selection and singleton lifecycle."""

import contextlib
import logging
import threading

from .base import YoloBackend

logger = logging.getLogger(__name__)

_ALL_BACKENDS: list[type[YoloBackend]] = []

_backends_loaded = False
_lock = threading.Lock()
_current_instance: YoloBackend | None = None
_current_key: str | None = None


def register_backend(cls: type[YoloBackend]) -> type[YoloBackend]:
    """Class decorator that registers a backend implementation."""
    _ALL_BACKENDS.append(cls)
    return cls


def _ensure_backends_loaded() -> None:
    """Lazy-import backend modules so their @register_backend decorators fire."""
    global _backends_loaded
    if _backends_loaded:
        return
    _backends_loaded = True
    # Each import may fail if the dependency is absent — that is fine.
    with contextlib.suppress(ImportError):
        from . import backend_hailo  # noqa: F401
    with contextlib.suppress(ImportError):
        from . import backend_onnx  # noqa: F401
    with contextlib.suppress(ImportError):
        from . import backend_opencv_dnn  # noqa: F401


def detect_available_backends() -> list[type[YoloBackend]]:
    """Return available backends sorted by priority descending."""
    _ensure_backends_loaded()
    available = [b for b in _ALL_BACKENDS if b.is_available()]
    available.sort(key=lambda b: b.priority(), reverse=True)
    return available


def get_backend(
    backend_pref: str = "auto", model_name: str = "yolov8n"
) -> YoloBackend:
    """Return (or create) a singleton backend instance.

    Args:
        backend_pref: Backend name or "auto" for highest-priority available.
        model_name: YOLO model to load.

    Returns:
        A ready-to-use YoloBackend instance.

    Raises:
        RuntimeError: If no backend is available.
    """
    global _current_instance, _current_key
    _ensure_backends_loaded()

    key = f"{backend_pref}:{model_name}"

    with _lock:
        # Reuse existing singleton if the request matches.
        if _current_instance is not None and _current_key == key:
            return _current_instance

        available = detect_available_backends()
        if not available:
            raise RuntimeError("No YOLO backend is available on this system.")

        chosen_cls: type[YoloBackend] | None = None

        if backend_pref == "auto":
            # Pick highest-priority backend that supports the model.
            for b in available:
                if model_name in b.supported_models():
                    chosen_cls = b
                    break
            if chosen_cls is None:
                raise RuntimeError(
                    f"No backend supports model '{model_name}'. "
                    f"Available backends: {[b.name for b in available]}"
                )
        else:
            # Try to find the explicitly requested backend.
            for b in available:
                if b.name == backend_pref:
                    chosen_cls = b
                    break
            if chosen_cls is None:
                # Fallback to auto when the requested backend is unavailable.
                logger.warning(
                    "Backend '%s' unavailable, falling back to auto",
                    backend_pref,
                )
                for b in available:
                    if model_name in b.supported_models():
                        chosen_cls = b
                        break
                if chosen_cls is None:
                    raise RuntimeError(
                        f"No backend supports model '{model_name}'."
                    )
            elif model_name not in chosen_cls.supported_models():
                raise ValueError(
                    f"Backend '{chosen_cls.name}' does not support "
                    f"model '{model_name}'. "
                    f"Supported: {chosen_cls.supported_models()}"
                )

        # Close old instance before creating a new one.
        if _current_instance is not None:
            _current_instance.close()
            _current_instance = None
            _current_key = None

        instance = chosen_cls()
        instance.load_model(model_name)
        _current_instance = instance
        _current_key = key
        logger.info(
            "YOLO backend ready: %s (model=%s)", chosen_cls.name, model_name
        )
        return instance


def close_backend() -> None:
    """Close and clear the current singleton backend."""
    global _current_instance, _current_key
    with _lock:
        if _current_instance is not None:
            _current_instance.close()
            _current_instance = None
            _current_key = None


def get_current_backend() -> YoloBackend | None:
    """Return the current backend instance, or None if not initialised."""
    return _current_instance
