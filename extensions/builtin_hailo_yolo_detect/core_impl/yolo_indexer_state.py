"""Shared state and lifecycle helpers for YOLO indexing."""

import logging
import threading
import time

from core.event_bus import emit

logger = logging.getLogger(__name__)

state_lock = threading.Lock()
detect_thread: threading.Thread | None = None
stop_requested = False
last_backend_name: str = ""
progress = {
    "running": False,
    "total": 0,
    "processed": 0,
    "errors": 0,
    "started_at": 0.0,
    "elapsed": 0.0,
    "message": "",
}


def get_detect_thread() -> threading.Thread | None:
    return detect_thread


def set_detect_thread(thread: threading.Thread | None) -> None:
    global detect_thread
    detect_thread = thread


def get_stop_requested() -> bool:
    return stop_requested


def set_stop_requested(value: bool) -> None:
    global stop_requested
    stop_requested = value


def get_last_backend_name() -> str:
    return last_backend_name


def set_last_backend_name(value: str) -> None:
    global last_backend_name
    last_backend_name = value


def finish_detection(reason: str, processed: int = 0, errors: int = 0, total: int = 0) -> None:
    """Clean up after detection completes or stops."""
    elapsed = time.time() - progress.get("started_at", time.time())
    with state_lock:
        progress["running"] = False
        progress["elapsed"] = round(elapsed, 1)
        progress["message"] = reason

    # Drop status caches now that detected/undetected counts have changed.
    # These COUNT(*)/COUNT(DISTINCT) queries cost 25-46s on production-scale
    # file_annotations; reliable invalidation here lets the SWR fresh window
    # be widened safely (no other writers touch these counts).
    try:
        from .yolo_indexer_queries import invalidate_yolo_detect_count_cache
        invalidate_yolo_detect_count_cache()
    except Exception:
        logger.exception("failed to invalidate yolo detect count cache")
    try:
        # Late import to avoid circular: hailo_yolo_detect imports from core_impl.
        from extensions.builtin_hailo_yolo_detect.hailo_yolo_detect import (
            invalidate_status_swr_caches,
        )
        invalidate_status_swr_caches()
    except Exception:
        logger.exception("failed to invalidate yolo status SWR caches")

    # Reconcile the db_meta rolling counters in the background. The COUNT
    # itself is 25-46s on production DBs but runs on a daemon thread against a
    # read-only connection, so finish_detection returns immediately. Status
    # API readers (1ms meta lookup) get the fresh values once persistence
    # completes; until then the in-memory TTL cache (also seeded by
    # recompute_and_persist_yolo_counts) covers the gap.
    def _reconcile():
        try:
            from .yolo_indexer_queries import recompute_and_persist_yolo_counts

            # Reconcile the active model. Other models stay stale until
            # someone reads them — count_detected/count_undetected fall back
            # to recompute on demand, so this is safe.
            try:
                from core.extensions_core.extensions_admin import get_extension_config_value
                model = get_extension_config_value(
                    "builtin-hailo-yolo-detect", "model", "yolov8n"
                )
            except Exception:
                model = "yolov8n"
            recompute_and_persist_yolo_counts(model)
        except Exception:
            logger.debug("yolo count reconcile after finish_detection failed", exc_info=True)

    threading.Thread(
        target=_reconcile, daemon=True, name="yolo-count-reconcile"
    ).start()

    emit(
        "yolo_detect.complete",
        {
            "reason": reason,
            "processed": processed,
            "errors": errors,
            "total": total,
            "elapsed_seconds": round(elapsed, 1),
        },
        source="yolo_detector",
    )
    logger.info("YOLO detection %s: %d/%d processed, %d errors, %.1fs", reason, processed, total, errors, elapsed)
