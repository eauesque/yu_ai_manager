"""Archive-file YOLO detection loop."""

import json
import logging
import time

from core.event_bus import emit

from .yolo_detector_workers import detect_archive_video, group_by_archive

logger = logging.getLogger(__name__)


def run_archive_detection(
    model_name: str,
    batch_size: int,
    conf_threshold: float,
    video_frame_interval: float,
    backend_pref: str = "auto",
    progress: dict | None = None,
    state_lock=None,
    stop_requested_fn=None,
    finish_fn=None,
    distributed: bool = False,
    media_filter: str = "all",
):
    """YOLO detection for archive-internal files."""
    from importlib import import_module as _im

    from core.files_core.media_types import is_video_file

    from .backends.backend_registry import close_backend, get_backend
    from .yolo_indexer import annotation_source as _annotation_source
    from .yolo_indexer import clear_skip_annotations as _clear_skip_annotations
    from .yolo_indexer import count_undetected_archive as _count_undetected_archive
    from .yolo_indexer import get_undetected_archive_ids as _get_undetected_archive_ids
    from .yolo_preprocess import preprocess_image_yolo

    ann_mod = _im("extensions.builtin_annotations.core_impl")
    set_annotations_batch = ann_mod.set_annotations_batch

    with state_lock:
        progress["running"] = True
        progress["processed"] = 0
        progress["errors"] = 0
        progress["started_at"] = progress.get("started_at") or time.time()
        progress["message"] = "Preparing archive detection"

    source = _annotation_source(model_name)
    cleared = _clear_skip_annotations(source)
    logger.info("Cleared %d archive skip markers for source=%s", cleared, source)

    with state_lock:
        progress["message"] = "Counting undetected archive files"

    initial_undetected = _count_undetected_archive(model_name, media_filter)
    total = initial_undetected
    with state_lock:
        progress["total"] = total
    if total == 0:
        finish_fn("No undetected archive files")
        return

    # Pause the live stream pipeline only after work is confirmed.  Concurrent
    # configured.run() calls from both threads can deadlock HailoRT internals.
    from .stream.stream_context import get_pipeline_if_active
    _stream_pipeline = get_pipeline_if_active()
    if _stream_pipeline is not None:
        logger.info("Pausing stream pipeline for archive batch detection")
        _stream_pipeline.request_batch_pause()
        released = _stream_pipeline.wait_batch_backend_released(timeout=15.0)
        if not released:
            logger.warning("Stream pipeline did not release backend within 15 s; proceeding anyway")

    emit(
        "yolo_detect.start",
        {"total": total, "model": model_name, "batch_size": batch_size, "mode": "archive"},
        source="yolo_detector",
    )
    logger.info("Starting archive YOLO detection: %d files, model=%s, filter=%s", total, model_name, media_filter)

    try:
        with state_lock:
            progress["message"] = "Initializing YOLO backend"
        detector = get_backend(backend_pref, model_name)
    except Exception as exc:
        logger.error("Failed to init YOLO detector: %s", exc)
        if _stream_pipeline is not None:
            _stream_pipeline.release_batch_pause()
        finish_fn(f"Detector init failed: {exc}")
        return

    with state_lock:
        progress["message"] = "Detecting"

    errors = 0
    infer_batch = min(batch_size, 16)
    stall_count = 0
    prev_remaining = initial_undetected

    while not stop_requested_fn():
        rows = _get_undetected_archive_ids(model_name, media_filter, limit=batch_size)
        if not rows:
            break
        groups = group_by_archive(rows)
        for _archive_path, items in groups.items():
            if stop_requested_fn():
                break
            batch_annotations = []
            image_items = []
            video_items = []
            for fid, full_path in items:
                if is_video_file(full_path):
                    video_items.append((fid, full_path))
                else:
                    image_items.append((fid, full_path))

            i = 0
            while i < len(image_items) and not stop_requested_fn():
                chunk = image_items[i : i + infer_batch]
                i += len(chunk)
                images = []
                scale_infos = []
                valid_fids = []
                for fid, full_path in chunk:
                    try:
                        img, scale_info = preprocess_image_yolo(full_path, detector.input_size)
                        images.append(img)
                        scale_infos.append(scale_info)
                        valid_fids.append(fid)
                    except Exception as exc:
                        logger.debug("Archive preprocess failed %d: %s", fid, exc)
                        errors += 1
                        batch_annotations.append({"file_id": fid, "source": source, "key": "detections", "value": "[]"})
                if not images:
                    continue

                try:
                    batch_results = detector.detect_batch(images, scale_infos, conf_threshold)
                except Exception as exc:
                    logger.error("Batch inference failed: %s", exc)
                    batch_results = []
                    for img, scale_info in zip(images, scale_infos, strict=False):
                        try:
                            batch_results.append(detector.detect(img, scale_info, conf_threshold))
                        except Exception:
                            batch_results.append(None)

                for idx, fid in enumerate(valid_fids):
                    detections = batch_results[idx] if idx < len(batch_results) else None
                    if detections is None:
                        errors += 1
                        batch_annotations.append({"file_id": fid, "source": source, "key": "detections", "value": "[]"})
                        continue
                    avg_conf = sum(det["confidence"] for det in detections) / len(detections) if detections else 0.0
                    batch_annotations.append(
                        {
                            "file_id": fid,
                            "source": source,
                            "key": "detections",
                            "value": json.dumps(detections, ensure_ascii=False),
                            "confidence": round(avg_conf, 4) if detections else None,
                        }
                    )

            for fid, full_path in video_items:
                if stop_requested_fn():
                    break
                try:
                    detections = detect_archive_video(detector, full_path, conf_threshold, video_frame_interval)
                    avg_conf = sum(det["confidence"] for det in detections) / len(detections) if detections else 0.0
                    batch_annotations.append(
                        {
                            "file_id": fid,
                            "source": source,
                            "key": "detections",
                            "value": json.dumps(detections, ensure_ascii=False),
                            "confidence": round(avg_conf, 4) if detections else None,
                        }
                    )
                except Exception as exc:
                    logger.debug("Archive video failed %d: %s", fid, exc)
                    errors += 1
                    batch_annotations.append({"file_id": fid, "source": source, "key": "detections", "value": "[]"})

            if batch_annotations:
                try:
                    set_annotations_batch(batch_annotations)
                except Exception as exc:
                    logger.error("Failed to save annotations: %s", exc)

        remaining = _count_undetected_archive(model_name, media_filter)
        processed = initial_undetected - remaining
        with state_lock:
            progress["processed"] = processed
            progress["errors"] = errors

        pct = round(processed / total * 100, 1) if total > 0 else 0
        elapsed = round(time.time() - progress["started_at"], 1)
        emit(
            "yolo_detect.progress",
            {"processed": processed, "total": total, "errors": errors, "percent": pct, "elapsed": elapsed},
            source="yolo_detector",
        )

        if remaining >= prev_remaining:
            stall_count += 1
            if stall_count >= 3:
                logger.error("Archive detection stalled (remaining=%d), stopping", remaining)
                break
        else:
            stall_count = 0
        prev_remaining = remaining

    close_backend()
    if _stream_pipeline is not None:
        _stream_pipeline.release_batch_pause()
        logger.info("Stream pipeline released from archive batch pause")
    reason = "stopped" if stop_requested_fn() else "complete"
    finish_fn(reason, initial_undetected - prev_remaining, errors, total)
