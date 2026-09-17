"""Main-file YOLO detection loop."""

import json
import logging
import time

from core.event_bus import emit

from .yolo_detector_workers import (
    detect_video,
    is_processable_file,
    mark_unprocessable_bulk,
    process_images_distributed,
)

logger = logging.getLogger(__name__)


def run_detection(
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
) -> None:
    """Main detection loop (background thread)."""
    from concurrent.futures import ThreadPoolExecutor
    from importlib import import_module as _im

    from core.files_core.media_types import is_video_file

    from .backends.backend_registry import close_backend, get_backend
    from .yolo_indexer import annotation_source as _annotation_source
    from .yolo_indexer import count_undetected as _count_undetected
    from .yolo_indexer import get_file_paths as _get_file_paths
    from .yolo_indexer import get_undetected_ids as _get_undetected_ids
    from .yolo_preprocess import preprocess_image_yolo

    ann_mod = _im("extensions.builtin_annotations.core_impl")
    set_annotations_batch = ann_mod.set_annotations_batch

    with state_lock:
        progress["running"] = True
        progress["processed"] = 0
        progress["errors"] = 0
        progress["started_at"] = progress.get("started_at") or time.time()
        progress["message"] = "Counting undetected files"

    pre_source = _annotation_source(model_name)
    bulk_skipped = mark_unprocessable_bulk(pre_source)
    if bulk_skipped:
        logger.info("Pre-marked %d unprocessable files as detected", bulk_skipped)

    initial_undetected = _count_undetected(model_name)
    total = initial_undetected
    with state_lock:
        progress["total"] = total
    if total == 0:
        finish_fn("No undetected files")
        return

    try:
        hailo_inf = _im("extensions.builtin_hailo_semantic_search.core_impl.hailo_inference")
        hailo_inf.close_encoder()
    except Exception:
        logger.warning("hailo encoder was not closed", exc_info=True)

    # Pause the live stream pipeline only after work is confirmed.  Concurrent
    # configured.run() calls from both threads can deadlock HailoRT internals.
    from .stream.stream_context import get_pipeline_if_active
    _stream_pipeline = get_pipeline_if_active()
    if _stream_pipeline is not None:
        logger.info("Pausing stream pipeline for batch detection")
        _stream_pipeline.request_batch_pause()
        released = _stream_pipeline.wait_batch_backend_released(timeout=15.0)
        if not released:
            logger.warning("Stream pipeline did not release backend within 15 s; proceeding anyway")

    emit("yolo_detect.start", {"total": total, "model": model_name, "batch_size": batch_size}, source="yolo_detector")
    logger.info("Starting YOLO detection: %d files, model=%s, batch=%d", total, model_name, batch_size)

    try:
        with state_lock:
            progress["message"] = "Initializing YOLO backend"
        detector = get_backend(backend_pref, model_name)
    except Exception as exc:
        if distributed:
            logger.warning("Local YOLO backend unavailable (%s), using remote-only", exc)
            detector = None
        else:
            logger.error("Failed to init YOLO detector: %s", exc)
            if _stream_pipeline is not None:
                _stream_pipeline.release_batch_pause()
            finish_fn(f"Detector init failed: {exc}")
            return

    with state_lock:
        progress["message"] = "Detecting"

    source = _annotation_source(model_name) if detector is not None else f"remote:{model_name}"
    processed = 0
    errors = 0
    failed_ids: set = set()
    infer_batch = min(batch_size, 16)
    preprocess_pool: ThreadPoolExecutor | None = None
    try:
        preprocess_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="yolo_pre")
        stall_count = 0
        prev_remaining = initial_undetected

        while not stop_requested_fn():
            file_ids = [fid for fid in _get_undetected_ids(model_name, limit=batch_size) if fid not in failed_ids]
            if not file_ids:
                break
            paths_map = _get_file_paths(file_ids)
            batch_annotations = []
            image_items = []
            video_items = []
            skip_annotations = []
            for fid in file_ids:
                if stop_requested_fn():
                    break
                path = paths_map.get(fid)
                if not path or not is_processable_file(path):
                    skip_annotations.append({"file_id": fid, "source": source, "key": "detections", "value": "[]"})
                    continue
                if is_video_file(path):
                    video_items.append((fid, path))
                else:
                    image_items.append((fid, path))
            if skip_annotations:
                set_annotations_batch(skip_annotations)
                errors += len(skip_annotations)

            if distributed and image_items:
                dist_processed, dist_errors = process_images_distributed(
                    image_items, detector, conf_threshold, batch_size, source, set_annotations_batch, stop_requested_fn
                )
                processed += dist_processed
                errors += dist_errors
                if dist_processed > 0 or dist_errors > 0:
                    image_items = []

            i = 0
            while i < len(image_items) and not stop_requested_fn():
                chunk = image_items[i : i + infer_batch]
                i += len(chunk)
                images = []
                scale_infos = []
                valid_fids = []

                def _preprocess(item):
                    fid, path = item
                    return fid, preprocess_image_yolo(path, detector.input_size)

                futures = {preprocess_pool.submit(_preprocess, item): item[0] for item in chunk}
                for future in futures:
                    fid = futures[future]
                    try:
                        _, (img, scale_info) = future.result()
                        images.append(img)
                        scale_infos.append(scale_info)
                        valid_fids.append(fid)
                    except Exception as exc:
                        logger.debug("Preprocess failed %d: %s", fid, exc)
                        errors += 1
                        failed_ids.add(fid)
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
                        failed_ids.add(fid)
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

            for fid, path in video_items:
                if stop_requested_fn():
                    break
                try:
                    detections = detect_video(detector, path, conf_threshold, video_frame_interval)
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
                    logger.debug("Failed to detect video %d (%s): %s", fid, path, exc)
                    errors += 1
                    failed_ids.add(fid)
                    batch_annotations.append({"file_id": fid, "source": source, "key": "detections", "value": "[]"})

            if batch_annotations:
                try:
                    set_annotations_batch(batch_annotations)
                    processed += len(batch_annotations)
                except Exception as exc:
                    logger.error("Failed to save annotations batch: %s", exc)
                    errors += len(batch_annotations)
                    for ann in batch_annotations:
                        failed_ids.add(ann["file_id"])

            remaining = _count_undetected(model_name)
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
                    logger.error("Detection stalled: no progress for %d batches (remaining=%d), stopping", stall_count, remaining)
                    break
            else:
                stall_count = 0
            prev_remaining = remaining

            if processed % 200 == 0 and processed > 0:
                logger.info("YOLO detection progress: %d/%d (%.1f%%), %d errors", processed, total, pct, errors)

    finally:
        if preprocess_pool is not None:
            preprocess_pool.shutdown(wait=False)
        close_backend()
        if _stream_pipeline is not None:
            _stream_pipeline.release_batch_pause()
            logger.info("Stream pipeline released from batch pause")
    reason = "stopped" if stop_requested_fn() else "complete"
    finish_fn(reason, processed, errors, total)
