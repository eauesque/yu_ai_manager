"""VLM batch caption generator for CLIP search results.

Runs VLM captioning in a background thread, saving results to
file_annotations with source="hailo:vlm", key="caption".
Follows the same threading pattern as indexer.py.
"""

import logging
import threading
import time

from core.event_bus import emit

logger = logging.getLogger(__name__)

# Caption state (thread-safe)
_state_lock = threading.Lock()
_caption_thread: threading.Thread | None = None
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


def get_caption_status() -> dict:
    """Get current captioning status."""
    with _state_lock:
        status = dict(_progress)
    if status["running"] and status["started_at"]:
        status["elapsed"] = round(time.time() - status["started_at"], 1)
    return status


def start_captioning(
    file_ids: list[int],
    prompt: str = "Describe this image in detail.",
    model: str = "qwen2-vl-2b-instruct",
) -> dict:
    """Start background VLM captioning. Returns status dict."""
    global _caption_thread, _stop_requested

    with _state_lock:
        if _progress["running"]:
            return {"status": "already_running", **_progress}
        _stop_requested = False

    if not file_ids:
        return {"status": "no_files", "message": "No file IDs provided"}

    _caption_thread = threading.Thread(
        target=_run_captioning,
        args=(file_ids, prompt, model),
        name="vlm-captioner",
        daemon=True,
    )
    _caption_thread.start()
    return {"status": "started", "total": len(file_ids)}


def stop_captioning() -> dict:
    """Request captioning to stop."""
    global _stop_requested
    with _state_lock:
        if not _progress["running"]:
            return {"status": "not_running"}
        _stop_requested = True
    return {"status": "stopping"}


def _run_captioning(
    file_ids: list[int],
    prompt: str,
    model: str,
) -> None:
    """Main captioning loop (runs in background thread)."""
    import importlib.util
    from pathlib import Path

    import cv2

    # Relative import within same extension's core_impl
    from .vector_store import get_file_paths_by_ids
    # Load from the Hailo GenAI extension module by file path.
    _spec = importlib.util.spec_from_file_location(
        "hailo_genai_vlm_inference",
        Path(__file__).resolve().parents[2] / "builtin_hailo_genai" / "core_impl" / "vlm_inference.py")
    _vlm_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_vlm_mod)
    get_vlm = _vlm_mod.get_vlm
    preprocess_image = _vlm_mod.preprocess_image

    global _stop_requested

    total = len(file_ids)

    with _state_lock:
        _progress["running"] = True
        _progress["processed"] = 0
        _progress["errors"] = 0
        _progress["total"] = total
        _progress["started_at"] = time.time()

    emit(
        "vlm_caption.start",
        {"total": total, "model": model},
        source="vlm_captioner",
    )
    logger.info("Starting VLM captioning: %d files, model=%s", total, model)

    try:
        vlm = get_vlm(model)
    except Exception as exc:
        logger.error("Failed to initialize VLM: %s", exc)
        _finish_captioning(f"VLM init failed: {exc}")
        return

    processed = 0
    errors = 0
    failed_ids: set = set()

    paths_map = get_file_paths_by_ids(file_ids)

    # Build VLM prompt structure
    vlm_prompt = [
        {"type": "text", "text": prompt},
    ]

    for fid in file_ids:
        if _stop_requested:
            break

        path = paths_map.get(fid)
        if not path:
            errors += 1
            failed_ids.add(fid)
            continue

        if fid in failed_ids:
            continue

        try:
            img_bgr = cv2.imread(path)
            if img_bgr is None:
                raise ValueError(f"Cannot read image: {path}")
            frame = preprocess_image(img_bgr)

            vlm.clear_context()
            caption = vlm.generate_all(vlm_prompt, frames=[frame])

            if caption and caption.strip():
                _save_caption(fid, caption.strip())
                processed += 1
            else:
                errors += 1
                failed_ids.add(fid)
        except Exception as exc:
            logger.debug("Failed to caption file %d (%s): %s", fid, path, exc)
            errors += 1
            failed_ids.add(fid)

        with _state_lock:
            _progress["processed"] = processed
            _progress["errors"] = errors

        pct = round((processed + errors) / total * 100, 1) if total > 0 else 0
        elapsed = round(time.time() - _progress["started_at"], 1)
        emit(
            "vlm_caption.progress",
            {
                "processed": processed,
                "total": total,
                "errors": errors,
                "percent": pct,
                "elapsed": elapsed,
            },
            source="vlm_captioner",
        )

    reason = "stopped" if _stop_requested else "complete"
    _finish_captioning(reason, processed, errors, total)


def _save_caption(file_id: int, caption: str) -> None:
    """Save a single caption to file_annotations."""
    # Import from relocated annotations extension
    from importlib import import_module
    _ann_store = import_module("extensions.builtin_annotations.core_impl.store")
    upsert_annotations_batch_commit = _ann_store.upsert_annotations_batch_commit

    upsert_annotations_batch_commit([{
        "file_id": file_id,
        "source": "hailo:vlm",
        "key": "caption",
        "value": caption,
        "confidence": None,
    }])


def _finish_captioning(
    reason: str,
    processed: int = 0,
    errors: int = 0,
    total: int = 0,
) -> None:
    """Clean up after captioning completes or stops."""
    elapsed = time.time() - _progress.get("started_at", time.time())

    with _state_lock:
        _progress["running"] = False
        _progress["elapsed"] = round(elapsed, 1)
        _progress["message"] = reason

    emit(
        "vlm_caption.complete",
        {
            "reason": reason,
            "processed": processed,
            "errors": errors,
            "total": total,
            "elapsed_seconds": round(elapsed, 1),
        },
        source="vlm_captioner",
    )
    logger.info(
        "VLM captioning %s: %d/%d processed, %d errors, %.1fs",
        reason, processed, total, errors, elapsed,
    )
