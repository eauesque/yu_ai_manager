"""Semantic Search extension entry point (Hailo / ONNX)."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from quart import Blueprint

from .hailo_semantic_search_model_routes import register_model_routes
from .hailo_semantic_search_page_routes import register_page_routes
from .hailo_semantic_search_search_routes import register_search_routes
from .hailo_semantic_search_status_routes import register_status_routes


def get_blueprint():
    bp = Blueprint("ext_hailo_semantic", __name__, template_folder="templates")
    register_page_routes(bp)
    register_status_routes(bp)
    register_search_routes(bp)
    register_model_routes(bp)
    return bp


def get_health() -> dict:
    """Unified health probe — consumed by /api/extensions.

    Available = any CLIP backend (ONNX, CoreML, or Hailo) is ready.
    Hailo-specific checks are shown as informational, not gating.
    """
    from core.hailo_device_core.hailo_health import base_checks

    from .core_impl.hailo_inference import _DEFAULT_HEF_DIR, _IMAGE_ENCODER_HEF

    # ONNX / CoreML / Hailo backend survey
    try:
        from extensions.builtin_clip_search.core_impl.encoder_factory import get_encoder_info
        info = get_encoder_info()
        any_available = info.get("any_available", False)
        onnx_ok = any(b.get("available") and b.get("name") == "onnx" for b in info.get("backends", []))
    except Exception:
        any_available = False
        onnx_ok = False

    # Hailo-specific sub-checks (informational)
    runtime_ok, hardware_ok = base_checks()
    hef_ok = (Path(_DEFAULT_HEF_DIR) / _IMAGE_ENCODER_HEF).exists()
    hailo_npu = runtime_ok and hardware_ok and hef_ok

    if any_available and not hailo_npu:
        reason = "Hailo NPU unavailable — running on ONNX/CoreML"
        key = "hailo.reason.onnx_fallback"
    elif not any_available:
        reason = "No CLIP backend available (install ONNX or connect Hailo device)"
        key = "hailo.reason.no_backend"
    else:
        reason = ""
        key = ""

    return {
        "available": any_available,
        "checks": {"onnx_ok": onnx_ok, "hailo_npu": hailo_npu},
        "reason": reason,
        "reason_i18n_key": key,
    }


__all__ = ["get_blueprint", "get_health"]
