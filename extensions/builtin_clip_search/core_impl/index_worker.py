"""Background indexing worker for CLIP semantic search.

Uses ImagePrefetcher for parallel I/O + ONNX encode_batch() for
batch inference — typically 4-10x faster than sequential processing.
"""

import logging
import time
from collections.abc import Callable

import numpy as np

from core.event_bus import emit

from .index_worker_images import process_images_distributed, process_images_pipelined

logger = logging.getLogger(__name__)

# Page size for fetching unindexed IDs from DB
_PAGE_SIZE = 4000
# Default parallel I/O workers
_PREFETCH_WORKERS = 10


def encode_video(path: str, encoder, preprocess_fn, file_id: int):
    """Encode a video file, returning a mean vector across keyframes."""
    from core.configuration.json_rw import load_config_json
    from core.files_core.video_keyframes import video_keyframes_context

    full_cfg = load_config_json(None)
    va_cfg = full_cfg.get("video_analysis", {})
    kf_count = va_cfg.get("keyframe_count", 4)
    strategy = va_cfg.get("strategy", "uniform")
    scene_th = va_cfg.get("scene_threshold", 0.4)
    store_per_kf = va_cfg.get("store_per_keyframe", False)

    with video_keyframes_context(
        path, count=kf_count, strategy=strategy, scene_threshold=scene_th,
    ) as frames:
        if not frames:
            raise ValueError("No keyframes extracted")
        vecs = []
        for f in frames:
            img = preprocess_fn(str(f))
            vecs.append(encoder.encode(img))

    if len(vecs) == 1:
        mean_vec = vecs[0]
    else:
        stacked = np.stack(vecs)
        mean_vec = stacked.mean(axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm > 1e-12:
            mean_vec = mean_vec / norm

    if store_per_kf:
        try:
            from core.files_core.video_keyframe_store import save_keyframe_results
            kf_data = []
            for idx, v in enumerate(vecs):
                kf_data.append({
                    "keyframe_idx": idx,
                    "timestamp_ms": 0,
                    "vector": v.tobytes(),
                })
            save_keyframe_results(file_id, kf_data, model="clip")
        except Exception as exc:
            logger.debug("Failed to save per-keyframe vectors for %d: %s", file_id, exc)

    return mean_vec


def run_indexing(
    batch_size: int,
    encoder_factory: Callable | None,
    preprocess_fn: Callable | None,
    progress: dict,
    state_lock,
    stop_requested_fn: Callable[[], bool],
    finish_fn: Callable,
    distributed: bool = False,
) -> None:
    """Main indexing loop with pipelined I/O and batch inference."""

    from .vector_store import (
        get_file_paths_by_ids,
        get_unindexed_file_ids_cursor,
        save_vectors_batch,
    )

    with state_lock:
        progress["running"] = True
        progress["processed"] = 0
        progress["errors"] = 0
        progress["started_at"] = progress.get("started_at") or time.time()
        progress["message"] = "Initializing semantic encoder"

    # Resolve encoder
    try:
        if encoder_factory is None or preprocess_fn is None:
            from .encoder_factory import get_best_encoder, get_preprocessor
            if encoder_factory is None:
                encoder_factory = get_best_encoder
            if preprocess_fn is None:
                _tmp_enc = encoder_factory()
                preprocess_fn = get_preprocessor(_tmp_enc)
                _resolved_encoder = _tmp_enc
            else:
                _resolved_encoder = None
        else:
            _resolved_encoder = None
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Failed to initialize encoder: %s", exc)
        finish_fn(f"Encoder init failed: {exc}")
        return

    with state_lock:
        progress["message"] = "Preparing semantic index"


    total = 0
    emit(
        "semantic_index.start",
        {"total": 0, "batch_size": batch_size},
        source="semantic_indexer",
    )
    logger.info(
        "Starting semantic indexing: batch_size=%d, workers=%d",
        batch_size, _PREFETCH_WORKERS,
    )

    try:
        encoder = _resolved_encoder or encoder_factory()
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Failed to initialize encoder: %s", exc)
        finish_fn(f"Encoder init failed: {exc}")
        return

    with state_lock:
        progress["message"] = "Indexing"

    processed = 0
    errors = 0
    last_progress_time = time.time()
    start_time = time.time()

    def _emit_progress():
        nonlocal last_progress_time
        with state_lock:
            progress["processed"] = processed
            progress["errors"] = errors
        pct = round(processed / total * 100, 1) if total > 0 else 0
        elapsed = round(time.time() - start_time, 1)
        rate = round(processed / elapsed, 1) if elapsed > 0 else 0
        emit(
            "semantic_index.progress",
            {
                "processed": processed,
                "total": total,
                "errors": errors,
                "percent": pct,
                "elapsed": elapsed,
                "rate": rate,
            },
            source="semantic_indexer",
        )
        last_progress_time = time.time()

    # ── Paged processing ────────────────────────────────────────────
    last_id = 0  # cursor for pagination

    while not stop_requested_fn():
        # Fetch a page of unindexed file IDs
        file_ids = get_unindexed_file_ids_cursor(
            after_id=last_id, limit=_PAGE_SIZE,
        )
        if not file_ids:
            break

        last_id = file_ids[-1]
        total += len(file_ids)
        with state_lock:
            progress["total"] = total
        paths_map = get_file_paths_by_ids(file_ids)

        # Separate images and videos
        image_items = []
        video_items = []
        for fid in file_ids:
            path = paths_map.get(fid)
            if not path:
                errors += 1
                continue
            from core.files_core.media_types import is_video_file
            if is_video_file(path):
                video_items.append((fid, path))
            else:
                image_items.append((fid, path))

        # ── Images: pipelined batch processing ──────────────────────
        if image_items and not stop_requested_fn():
            if distributed:
                page_processed, page_errors = process_images_distributed(
                    image_items, encoder, preprocess_fn, batch_size,
                    save_vectors_batch, stop_requested_fn,
                )
            else:
                page_processed, page_errors = process_images_pipelined(
                    image_items, encoder, batch_size,
                    save_vectors_batch, stop_requested_fn,
                )
            processed += page_processed
            errors += page_errors

            if time.time() - last_progress_time >= 3.0:
                _emit_progress()

        # ── Videos: sequential (keyframe extraction is inherently serial) ─
        for fid, path in video_items:
            if stop_requested_fn():
                break
            try:
                vec = encode_video(path, encoder, preprocess_fn, fid)
                save_vectors_batch([fid], np.stack([vec]))
                processed += 1
            except Exception as exc:
                logger.debug("Video encode failed %d: %s", fid, exc)
                errors += 1

            if time.time() - last_progress_time >= 3.0:
                _emit_progress()

        _emit_progress()

        if processed > 0 and processed % 5000 < _PAGE_SIZE:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total - processed) / rate if rate > 0 else 0
            logger.info(
                "Semantic index: %d/%d (%.1f%%), %d errors, %.1f/s, ETA %.0fm",
                processed, total,
                processed / total * 100 if total > 0 else 0,
                errors, rate, eta / 60,
            )

    reason = "stopped" if stop_requested_fn() else "complete"
    finish_fn(reason, processed, errors, total)
