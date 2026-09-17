import json
import logging

logger = logging.getLogger(__name__)


def _save_distributed_results(results, source, save_fn):
    """Build annotation dicts from detection results and persist via save_fn with retry."""
    if not results:
        return 0, 0
    annotations = []
    for fid, detections in results:
        if detections is None:
            continue
        avg_conf = sum(det["confidence"] for det in detections) / len(detections) if detections else 0.0
        annotations.append(
            {
                "file_id": fid,
                "source": source,
                "key": "detections",
                "value": json.dumps(detections, ensure_ascii=False),
                "confidence": round(avg_conf, 4) if detections else None,
            }
        )
    for retry in range(3):
        try:
            save_fn(annotations)
            return len(annotations), 0
        except Exception as exc:
            if "locked" in str(exc).lower() and retry < 2:
                import time

                time.sleep(3.0 * (retry + 1))
            else:
                logger.error("Distributed YOLO save failed: %s", exc)
                return 0, len(annotations)
    return 0, len(annotations)


def process_images_distributed(items, local_detector, conf_threshold, batch_size, source, save_fn, stop_fn) -> tuple:
    """Process images using mesh InferenceRouter + local detector fallback."""
    from core.mesh_inference import get_router
    from core.mesh_inference.dispatch_sync import dispatch_inference_sync

    router = get_router()
    has_local = local_detector is not None

    if router is None:
        if not has_local:
            logger.warning("Distributed YOLO: no workers available")
            return 0, len(items)
        processed = 0
        errors = 0
        for start in range(0, len(items), batch_size):
            if stop_fn():
                break
            batch = items[start : start + batch_size]
            valid_results, worker_skipped = _account_worker_results(
                detect_local_batch(batch, local_detector, conf_threshold),
                len(batch),
            )
            saved, failed = _save_distributed_results(
                valid_results,
                source, save_fn,
            )
            processed += saved
            errors += worker_skipped + failed
        return processed, errors

    processed = 0
    errors = 0
    local_peer_id = router._local_peer.peer_id

    async def worker_fn(peer, batch):
        if peer.peer_id == local_peer_id:
            if has_local:
                return detect_local_batch(batch, local_detector, conf_threshold)
            return [(fid, []) for fid, _ in batch]
        from core.mesh_inference._imports import yolo_detect_remote
        remote_items = [(fid, path) for fid, path in batch if "!" not in path]
        local_items = [(fid, path) for fid, path in batch if "!" in path]
        results = []
        if remote_items:
            paths = [path for _, path in remote_items]
            fids = [fid for fid, _ in remote_items]
            detections_list = await yolo_detect_remote(peer, paths)
            if detections_list is None:
                _log_dropped("Distributed YOLO remote", {"none": len(remote_items)})
                return None
            drop_counts: dict[str, int] = {}
            for fid, det in zip(fids, detections_list, strict=False):
                if det is None:
                    drop_counts["none"] = drop_counts.get("none", 0) + 1
                else:
                    results.append((fid, det))
            missing = max(len(remote_items) - len(detections_list), 0)
            if missing:
                drop_counts["missing"] = drop_counts.get("missing", 0) + missing
            _log_dropped("Distributed YOLO remote", drop_counts)
        if local_items and has_local:
            results.extend(detect_local_batch(local_items, local_detector, conf_threshold))
        return results

    def result_fn(results, batch):
        nonlocal processed, errors
        total = len(batch)
        valid_results, worker_skipped = _account_worker_results(results, total)
        saved, failed = _save_distributed_results(valid_results, source, save_fn)
        processed += saved
        errors += worker_skipped + failed
        _log_dropped(
            "Distributed YOLO result",
            {
                "worker_skipped": worker_skipped,
                "save_fail": failed,
            },
        )

    result = dispatch_inference_sync(
        router, "yolo", items,
        batch_size=batch_size, mode="parallel",
        worker_fn=worker_fn, result_fn=result_fn,
    )
    del result
    return processed, errors


def detect_local_batch(batch_items, detector, conf_threshold):
    from .yolo_preprocess import preprocess_image_yolo

    results = []
    for fid, path in batch_items:
        try:
            image, scale_info = preprocess_image_yolo(path, detector.input_size)
            results.append((fid, detector.detect(image, scale_info, conf_threshold)))
        except Exception as exc:
            logger.debug("Local detect skip fid=%d: %s", fid, exc)
            results.append(None)
    dropped = sum(1 for item in results if item is None)
    _log_dropped("Distributed YOLO local", {"detect_error": dropped})
    return results


def _account_worker_results(results, total: int):
    if not isinstance(results, (list, tuple)):
        return [], total
    none_items = sum(1 for item in results if item is None)
    missing = max(total - len(results), 0)
    worker_skipped = min(total, none_items + missing)
    capacity = max(total - worker_skipped, 0)
    valid_results = [item for item in results if item is not None][:capacity]
    extra = max(len(results) - total, 0)
    if extra:
        logger.warning("Distributed YOLO dropped %d extra worker results", extra)
    return valid_results, worker_skipped


def _log_dropped(context: str, counts: dict[str, int]) -> None:
    counts = {reason: count for reason, count in counts.items() if count}
    if not counts:
        return
    total = sum(counts.values())
    breakdown = ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))
    logger.warning("%s dropped %d items: %s", context, total, breakdown)
