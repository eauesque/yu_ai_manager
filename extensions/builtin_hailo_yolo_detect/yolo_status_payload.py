"""YOLO status payload builder."""

from __future__ import annotations

from core.extensions_core.extensions_admin import get_extension_config_value

_EXT_NAME = "builtin-hailo-yolo-detect"


def build_yolo_status_payload() -> dict:
    from core.hailo_device_core.device_manager import (
        get_current_owner,
        is_hailo_available,
    )

    from .core_impl.backends.backend_registry import (
        detect_available_backends,
        get_current_backend,
    )
    from .core_impl.model_download import get_model_status
    from .core_impl.yolo_indexer import get_detect_status

    detect_status = get_detect_status()
    backend = get_current_backend()
    available = detect_available_backends()
    return {
        "status": "ok",
        "hailo_available": is_hailo_available(),
        "any_backend_available": len(available) > 0,
        "device_owner": get_current_owner(),
        "models": get_model_status(),
        "detected_count": detect_status.get("detected", 0),
        "undetected_count": detect_status.get("undetected", 0),
        "detection_running": detect_status.get("running", False),
        "auto_detect_on_scan": get_extension_config_value(_EXT_NAME, "auto_detect_on_scan", False),
        "backend": backend.info() if backend else None,
        "available_backends": [
            {
                "name": cls.name,
                "priority": cls.priority(),
                "supported_models": cls.supported_models(),
            }
            for cls in available
        ],
        "config": {
            "backend": get_extension_config_value(_EXT_NAME, "backend", "auto"),
            "model": get_extension_config_value(_EXT_NAME, "model", "yolov8n"),
            "confidence_threshold": get_extension_config_value(_EXT_NAME, "confidence_threshold", 0.25),
            "batch_size": get_extension_config_value(_EXT_NAME, "batch_size", 16),
            "video_frame_interval": get_extension_config_value(_EXT_NAME, "video_frame_interval", 2.0),
        },
    }


def build_yolo_runtime_payload() -> dict:
    payload = build_yolo_status_payload()
    return {
        key: payload[key]
        for key in (
            "status",
            "models",
            "detected_count",
            "undetected_count",
            "detection_running",
            "auto_detect_on_scan",
            "config",
            "available_backends",
        )
    }
