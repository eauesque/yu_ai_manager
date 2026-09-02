"""Backward compatibility shim. Use backends.backend_registry instead."""

from .backends.backend_registry import close_backend
from .backends.backend_registry import get_backend as _get_backend


def get_detector(model_name="yolov8n", hef_dir=None):
    """Get a YOLO detector via the backend registry (Hailo preferred)."""
    return _get_backend("hailo", model_name)


def close_detector():
    """Close the current backend."""
    close_backend()


def is_yolo_hef_available(model_name="yolov8n"):
    """Check if Hailo HEF is available."""
    from .backends.backend_hailo import HailoBackend
    return HailoBackend.is_available()
