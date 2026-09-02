"""Runtime entrypoints for background YOLO indexing."""

import logging
import threading
import time

from .yolo_indexer_queries import (
    annotation_source as _annotation_source,
)
from .yolo_indexer_queries import (
    clear_skip_annotations as _clear_skip_annotations,
)
from .yolo_indexer_queries import (
    count_detected as _count_detected,
)
from .yolo_indexer_queries import (
    count_undetected as _count_undetected,
)
from .yolo_indexer_queries import (
    count_undetected_archive as _count_undetected_archive,
)
from .yolo_indexer_state import (
    finish_detection as _finish_detection,
)
from .yolo_indexer_state import (
    get_stop_requested as _get_stop_requested,
)
from .yolo_indexer_state import (
    progress as _progress,
)
from .yolo_indexer_state import (
    set_detect_thread as _set_detect_thread,
)
from .yolo_indexer_state import (
    set_stop_requested as _set_stop_requested,
)
from .yolo_indexer_state import (
    state_lock as _state_lock,
)

logger = logging.getLogger(__name__)


def get_detect_status() -> dict:
    """Get current detection status."""
    with _state_lock:
        status = dict(_progress)
    status["detected"] = _count_detected()
    status["undetected"] = _count_undetected()
    if status["running"] and status["started_at"]:
        status["elapsed"] = round(time.time() - status["started_at"], 1)
    return status


def start_detection(
    model_name: str = "yolov8n",
    batch_size: int = 16,
    conf_threshold: float = 0.25,
    video_frame_interval: float = 2.0,
    backend: str = "auto",
    distributed: bool = False,
    preflight: bool = True,
) -> dict:
    """Start background detection. Returns status dict."""
    from .yolo_detector import run_detection

    with _state_lock:
        if _progress["running"]:
            return {"status": "already_running", **_progress}
        _set_stop_requested(False)
        _progress["running"] = True
        _progress["total"] = 0
        _progress["processed"] = 0
        _progress["errors"] = 0
        _progress["started_at"] = time.time()
        _progress["elapsed"] = 0.0
        _progress["message"] = "Initializing YOLO detector"

    undetected = None
    if preflight:
        undetected = _count_undetected(model_name)
        if undetected == 0:
            with _state_lock:
                _progress["running"] = False
                _progress["message"] = "No undetected files found"
            return {"status": "no_files", "message": "No undetected files found"}
        with _state_lock:
            _progress["total"] = undetected

    _start_thread(
        name="yolo-detector",
        target=run_detection,
        args=(model_name, batch_size, conf_threshold, video_frame_interval, backend),
        kwargs={
            "progress": _progress,
            "state_lock": _state_lock,
            "stop_requested_fn": _get_stop_requested,
            "finish_fn": _finish_detection,
            "distributed": distributed,
        },
    )
    return {"status": "started", "total": undetected or 0}


def start_archive_detection(
    model_name: str = "yolov8n",
    batch_size: int = 16,
    conf_threshold: float = 0.25,
    video_frame_interval: float = 2.0,
    backend: str = "auto",
    distributed: bool = False,
    media_filter: str = "all",
    preflight: bool = True,
) -> dict:
    """Start background archive detection. Returns status dict."""
    from .yolo_detector import run_archive_detection

    with _state_lock:
        if _progress["running"]:
            return {"status": "already_running", **_progress}
        _set_stop_requested(False)
        _progress["running"] = True
        _progress["total"] = 0
        _progress["processed"] = 0
        _progress["errors"] = 0
        _progress["started_at"] = time.time()
        _progress["elapsed"] = 0.0
        _progress["message"] = "Initializing YOLO archive detector"

    undetected = None
    if preflight:
        source = _annotation_source(model_name)
        cleared = _clear_skip_annotations(source)
        logger.info("Cleared %d archive skip markers for source=%s", cleared, source)

        undetected = _count_undetected_archive(model_name, media_filter)
        if undetected == 0:
            with _state_lock:
                _progress["running"] = False
                _progress["message"] = "No undetected archive files found"
            return {"status": "no_files", "message": "No undetected archive files found"}
        with _state_lock:
            _progress["total"] = undetected

    _start_thread(
        name="yolo-archive-detector",
        target=run_archive_detection,
        args=(model_name, batch_size, conf_threshold, video_frame_interval, backend),
        kwargs={
            "progress": _progress,
            "state_lock": _state_lock,
            "stop_requested_fn": _get_stop_requested,
            "finish_fn": _finish_detection,
            "distributed": distributed,
            "media_filter": media_filter,
        },
    )
    return {"status": "started", "total": undetected or 0}


def stop_detection() -> dict:
    """Request detection to stop."""
    with _state_lock:
        if not _progress["running"]:
            return {"status": "not_running"}
        _set_stop_requested(True)
    return {"status": "stopping"}
def _start_thread(name: str, target, args: tuple, kwargs: dict) -> None:
    thread = threading.Thread(
        target=target,
        args=args,
        kwargs=kwargs,
        name=name,
        daemon=True,
    )
    _set_detect_thread(thread)
    thread.start()
