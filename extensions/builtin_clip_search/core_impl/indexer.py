"""Batch indexer for building CLIP embedding vectors.

Processes unindexed images through a CLIP image encoder (Hailo or ONNX)
in batches, storing results in the file_vectors table.

The encoder and preprocessing function are injected via
``encoder_factory`` and ``preprocess_fn`` parameters so that
callers can select the appropriate backend.

NOTE: The background indexing loop and video encoding have been moved
to index_worker.py. This module re-exports all public symbols for
backward compatibility.
"""

import logging
import threading
import time
from collections.abc import Callable

from core.event_bus import emit

from .index_worker import (  # noqa: F401 -- re-export
    encode_video as _encode_video,
)
from .index_worker import (
    run_indexing as _run_indexing_impl,
)

logger = logging.getLogger(__name__)

# Indexing state (thread-safe)
_state_lock = threading.Lock()
_indexing_thread: threading.Thread | None = None
_stop_requested = False
_progress = {
    "running": False,
    "total": 0,
    "processed": 0,
    "errors": 0,
    "started_at": 0.0,
    "elapsed": 0.0,
    "message": "",
}


def get_index_status() -> dict:
    """Get current indexing status."""
    with _state_lock:
        status = dict(_progress)

    status["indexed"] = status["processed"]
    status["unindexed"] = max(status["total"] - status["processed"], 0)
    if status["running"] and status["started_at"]:
        status["elapsed"] = round(time.time() - status["started_at"], 1)
    return status

def start_indexing(
    batch_size: int = 32,
    encoder_factory: Callable | None = None,
    preprocess_fn: Callable | None = None,
    distributed: bool = False,
    preflight: bool = True,
) -> dict:
    """Start background indexing. Returns status dict.

    Args:
        batch_size: Number of images per batch.
        encoder_factory: Callable returning a ClipImageEncoder instance.
            If None, uses encoder_factory module's default.
        preprocess_fn: Callable(path) -> preprocessed image array.
            If None, uses the preprocessor for the auto-selected backend.
        distributed: If True, use distributed inference workers for encoding.
        preflight: If True, refresh/count before returning. Async HTTP routes can
            set False to avoid blocking the event loop during DB checks.
    """
    global _indexing_thread, _stop_requested
    from core.services_core.clip_search_helper_service import is_clip_eligible_dirty

    from .vector_store import count_unindexed
    from .vector_store_support import refresh_clip_eligible

    with _state_lock:
        if _progress["running"]:
            return {"status": "already_running", **_progress}
        _stop_requested = False
        _progress["running"] = True
        _progress["total"] = 0
        _progress["processed"] = 0
        _progress["errors"] = 0
        _progress["started_at"] = time.time()
        _progress["elapsed"] = 0.0
        _progress["message"] = "Initializing semantic indexer"

    unindexed = None
    if preflight:
        # Rebuild only when this process has not yet synchronized helper-table state.
        if is_clip_eligible_dirty():
            refresh_clip_eligible()
        unindexed = count_unindexed()
        if unindexed == 0:
            with _state_lock:
                _progress["running"] = False
                _progress["message"] = "No unindexed files found"
            return {"status": "no_files", "message": "No unindexed files found"}
        with _state_lock:
            _progress["total"] = unindexed

    _indexing_thread = threading.Thread(
        target=_run_indexing,
        args=(batch_size, encoder_factory, preprocess_fn, distributed),
        name="semantic-indexer",
        daemon=True,
    )
    _indexing_thread.start()
    return {"status": "started", "total": unindexed or 0}


def stop_indexing() -> dict:
    """Request indexing to stop."""
    global _stop_requested
    with _state_lock:
        if not _progress["running"]:
            return {"status": "not_running"}
        _stop_requested = True
    return {"status": "stopping"}


def _run_indexing(
    batch_size: int,
    encoder_factory: Callable | None,
    preprocess_fn: Callable | None,
    distributed: bool = False,
) -> None:
    """Wrapper that delegates to index_worker.run_indexing with shared state."""
    _run_indexing_impl(
        batch_size=batch_size,
        encoder_factory=encoder_factory,
        preprocess_fn=preprocess_fn,
        distributed=distributed,
        progress=_progress,
        state_lock=_state_lock,
        stop_requested_fn=lambda: _stop_requested,
        finish_fn=_finish_indexing,
    )


def _finish_indexing(
    reason: str,
    processed: int = 0,
    errors: int = 0,
    total: int = 0,
) -> None:
    """Clean up after indexing completes or stops."""
    elapsed = time.time() - _progress.get("started_at", time.time())

    with _state_lock:
        _progress["running"] = False
        _progress["elapsed"] = round(elapsed, 1)
        _progress["message"] = reason

    emit(
        "semantic_index.complete",
        {
            "reason": reason,
            "processed": processed,
            "errors": errors,
            "total": total,
            "elapsed_seconds": round(elapsed, 1),
        },
        source="semantic_indexer",
    )
    logger.info(
        "Semantic indexing %s: %d/%d processed, %d errors, %.1fs",
        reason, processed, total, errors, elapsed,
    )
    # Drop the /api/status indexed/unindexed cache so the next poll picks up
    # the just-completed batch counts instead of returning a 5-min-fresh
    # stale snapshot. Late import keeps this module importable without the
    # hailo_semantic_search extension being loaded.
    try:
        from extensions.builtin_hailo_semantic_search.hailo_semantic_search_status_routes import (
            invalidate_sem_count_cache,
        )
        invalidate_sem_count_cache()
    except Exception:
        logger.debug("semantic status cache invalidate skipped", exc_info=True)
