"""Hailo-10H YOLO Object Detection extension entry point."""

import logging
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.extensions_core.extensions_admin import get_extension_config_value
from quart import Blueprint, jsonify, render_template, request

from core.infra_core.blocking_tasks import run_long_blocking_sync

from .yolo_routes_search import register_result_routes  # noqa: F401
from .yolo_status_payload import build_yolo_runtime_payload as _build_yolo_runtime_payload

_EXT_NAME = "builtin-hailo-yolo-detect"

_swr_lock = threading.Lock()
_yolo_detect_status_payload: dict | None = None
_yolo_detect_status_payload_ts: float = 0.0
_yolo_detect_status_refreshing: bool = False
_YOLO_DETECT_STATUS_FRESH_S = 300.0  # 5 min; was 5s


def _detection_running() -> bool:
    try:
        from .core_impl.yolo_indexer_state import progress as _progress
        return bool(_progress.get("running"))
    except Exception:
        return False


def _spawn_refresh(target):
    threading.Thread(target=target, daemon=True, name="yolo-swr-refresh").start()


def invalidate_status_swr_caches() -> None:
    global _yolo_detect_status_payload, _yolo_detect_status_payload_ts
    with _swr_lock:
        _yolo_detect_status_payload = None
        _yolo_detect_status_payload_ts = 0.0


def _warmup_status_caches() -> None:
    try:
        from .core_impl.yolo_indexer_queries import recompute_and_persist_yolo_counts

        model = get_extension_config_value(_EXT_NAME, "model", "yolov8n")
        recompute_and_persist_yolo_counts(model)
    except Exception:
        logger.debug("YOLO count reconcile skipped", exc_info=True)

    try:
        from .core_impl.yolo_indexer import get_detect_status
        result = get_detect_status()
        with _swr_lock:
            global _yolo_detect_status_payload, _yolo_detect_status_payload_ts
            _yolo_detect_status_payload = result
            _yolo_detect_status_payload_ts = time.time()
    except Exception:
        logger.debug("YOLO detect/status warm-up skipped", exc_info=True)


_warmup_started = False
_warmup_lock = threading.Lock()


def _ensure_warmup_started() -> None:
    global _warmup_started
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True
    threading.Thread(
        target=_warmup_status_caches, daemon=True, name="yolo-status-warmup"
    ).start()


def _refresh_yolo_detect_status() -> None:
    global _yolo_detect_status_payload, _yolo_detect_status_payload_ts, _yolo_detect_status_refreshing
    try:
        from .core_impl.yolo_indexer import get_detect_status
        result = get_detect_status()
        with _swr_lock:
            _yolo_detect_status_payload = result
            _yolo_detect_status_payload_ts = time.time()
    except Exception:
        logger.exception("YOLO detect/status background refresh failed")
    finally:
        with _swr_lock:
            _yolo_detect_status_refreshing = False


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def get_health() -> dict:
    """Unified health probe — consumed by /api/extensions.

    Available = any YOLO backend (ONNX, OpenCV DNN, or Hailo) is ready.
    Hailo-specific checks are informational, not gating.
    """
    from core.hailo_device_core.hailo_health import base_checks

    from .core_impl.backends.backend_registry import detect_available_backends
    from .core_impl.model_download import is_hef_available

    available_backends = detect_available_backends()
    any_available = len(available_backends) > 0
    onnx_ok = any(b.name == "onnx" for b in available_backends)

    # Hailo-specific sub-checks (informational)
    runtime_ok, hardware_ok = base_checks()
    model = get_extension_config_value(_EXT_NAME, "model", "yolov8n")
    hef_ok = is_hef_available(model)
    hailo_npu = runtime_ok and hardware_ok and hef_ok

    if any_available and not hailo_npu:
        best = available_backends[0].name if available_backends else "unknown"
        reason = f"Hailo NPU unavailable — running on {best}"
        key = "hailo.reason.onnx_fallback"
    elif not any_available:
        reason = "No YOLO backend available (install ONNX or connect Hailo device)"
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


def get_blueprint():
    _ensure_warmup_started()

    bp = Blueprint(
        "ext_hailo_yolo",
        __name__,
        template_folder="templates",
    )

    @bp.route("/")
    async def index():
        return await render_template("hailo_yolo_detect/yolo_detect.html")

    @bp.route("/api/runtime")
    async def api_runtime():
        """Return non-health runtime state for the tools UI."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        result = await run_long_blocking_sync(_build_yolo_runtime_payload)
        return jsonify(result)

    @bp.route("/api/detect/start", methods=["POST"])
    async def api_detect_start():
        """Start batch object detection."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.yolo_indexer import start_archive_detection, start_detection

        data = await request.get_json(silent=True) or {}
        model = data.get(
            "model",
            get_extension_config_value(_EXT_NAME, "model", "yolov8n"),
        )
        batch_size = int(data.get(
            "batch_size",
            get_extension_config_value(_EXT_NAME, "batch_size", 16),
        ))
        conf = float(data.get(
            "confidence_threshold",
            get_extension_config_value(_EXT_NAME, "confidence_threshold", 0.25),
        ))
        interval = float(data.get(
            "video_frame_interval",
            get_extension_config_value(_EXT_NAME, "video_frame_interval", 2.0),
        ))
        backend_pref = data.get(
            "backend",
            get_extension_config_value(_EXT_NAME, "backend", "auto"),
        )
        distributed = data.get("distributed", False)
        archive = data.get("archive", False)
        media_filter = data.get("media_filter", "all")

        logger.info(
            "detect/start: model=%s batch=%d distributed=%s archive=%s filter=%s",
            model, batch_size, distributed, archive, media_filter,
        )

        if archive:
            result = start_archive_detection(
                model_name=model,
                batch_size=batch_size,
                conf_threshold=conf,
                video_frame_interval=interval,
                backend=backend_pref,
                distributed=distributed,
                media_filter=media_filter,
                preflight=False,
            )
        else:
            result = start_detection(
                model_name=model,
                batch_size=batch_size,
                conf_threshold=conf,
                video_frame_interval=interval,
                backend=backend_pref,
                distributed=distributed,
                preflight=False,
            )
        return jsonify(result)

    @bp.route("/api/detect/status")
    async def api_detect_status():
        """Get detection progress."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.yolo_indexer import get_detect_status
        global _yolo_detect_status_payload, _yolo_detect_status_payload_ts, _yolo_detect_status_refreshing
        running = _detection_running()
        if not running:
            with _swr_lock:
                cached_payload = _yolo_detect_status_payload
                cached_age = time.time() - _yolo_detect_status_payload_ts if _yolo_detect_status_payload else None
                refreshing = _yolo_detect_status_refreshing
                if cached_payload is not None and cached_age is not None and cached_age > _YOLO_DETECT_STATUS_FRESH_S and not refreshing:
                    _yolo_detect_status_refreshing = True
                    spawn = True
                else:
                    spawn = False
            if cached_payload is not None:
                if spawn:
                    _spawn_refresh(_refresh_yolo_detect_status)
                payload = dict(cached_payload)
                if cached_age is not None and cached_age > _YOLO_DETECT_STATUS_FRESH_S:
                    payload["_stale"] = True
                return jsonify(payload)
        result = await run_long_blocking_sync(get_detect_status)
        if not running:
            with _swr_lock:
                _yolo_detect_status_payload = result
                _yolo_detect_status_payload_ts = time.time()
        return jsonify(result)

    @bp.route("/api/detect/stop", methods=["POST"])
    async def api_detect_stop():
        """Stop detection."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.yolo_indexer import stop_detection
        return jsonify(stop_detection())

    register_result_routes(bp)
    # Stream routes stay Rust-native only (T9); Python registration removed
    # after parity PASS. Only stream_persist.py remains as the schema oracle.
    return bp


__all__ = ["get_blueprint", "get_health"]
