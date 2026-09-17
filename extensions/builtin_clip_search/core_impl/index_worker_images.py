"""Image batch helpers for the CLIP semantic indexing worker."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)
_PREFETCH_WORKERS = 10
_warned_missing_output_dim = False


def process_images_pipelined(items: list, encoder, batch_size: int, save_fn: Callable, stop_fn: Callable[[], bool]) -> tuple:
    """Process images with prefetch pipeline + batch encode."""
    from core.batch_pipeline.prefetch import ImagePrefetcher
    from core.clip_onnx_core.preprocess import preprocess_image

    processed = 0
    batch_errors = 0
    with ImagePrefetcher(items, preprocess_image, workers=_PREFETCH_WORKERS) as prefetcher:
        while not stop_fn():
            batch = prefetcher.take_batch(batch_size, timeout=10.0)
            if not batch:
                break
            ids, arrays = zip(*batch, strict=False)
            ids = list(ids)
            try:
                vecs = encoder.encode_batch(np.stack(arrays))
            except Exception as exc:
                logger.warning("Batch encode failed (%d items): %s", len(ids), exc)
                ids, vecs, failed = _encode_fallback(ids, arrays, encoder)
                batch_errors += failed
                if not ids:
                    continue
            if _save_with_retry(ids, vecs, save_fn):
                processed += len(ids)
            else:
                batch_errors += len(ids)
        batch_errors += prefetcher.errors
    return processed, batch_errors


def process_images_distributed(items: list, local_encoder, local_preprocess_fn: Callable, batch_size: int, save_fn: Callable, stop_fn: Callable[[], bool]) -> tuple:
    """Process images using mesh InferenceRouter + local encoder fallback."""
    from core.mesh_inference import get_router
    from core.mesh_inference.dispatch_sync import dispatch_inference_sync

    router = get_router()
    if router is None:
        return process_images_pipelined(items, local_encoder, batch_size, save_fn, stop_fn)

    processed = 0
    errors = 0
    local_peer_id = router._local_peer.peer_id
    expected_dim = _expected_vector_dim(local_encoder)

    async def worker_fn(peer, batch):
        if peer.peer_id == local_peer_id:
            return encode_local_batch(batch, local_encoder, local_preprocess_fn, expected_dim)
        from core.mesh_inference._imports import clip_encode_remote
        remote_items = [(fid, path) for fid, path in batch if "!" not in path]
        local_items = [(fid, path) for fid, path in batch if "!" in path]
        results = []
        if remote_items:
            vectors = await clip_encode_remote(peer, [path for _, path in remote_items])
            if vectors is None:
                _log_dropped("Distributed CLIP remote", {"none": len(remote_items)}, expected_dim)
                return None
            drop_counts: dict[str, int] = {}
            for (fid, _), vec in zip(remote_items, vectors, strict=False):
                reason = _vector_skip_reason(vec, expected_dim)
                if reason is None:
                    results.append((fid, vec))
                else:
                    drop_counts[reason] = drop_counts.get(reason, 0) + 1
            missing = max(len(remote_items) - len(vectors), 0)
            if missing:
                drop_counts["missing"] = drop_counts.get("missing", 0) + missing
            _log_dropped("Distributed CLIP remote", drop_counts, expected_dim)
        if local_items:
            results.extend(encode_local_batch(local_items, local_encoder, local_preprocess_fn, expected_dim))
        return results

    def result_fn(results, batch):
        nonlocal processed, errors
        total = len(batch)
        valid_results, worker_skipped = _account_worker_results(results, total)
        saved = 0
        save_failures = 0
        if valid_results:
            ids = [fid for fid, _ in valid_results]
            vecs = np.stack([vec for _, vec in valid_results])
            if _save_with_retry(ids, vecs, save_fn):
                saved = len(ids)
            else:
                save_failures = len(ids)
        batch_errors = worker_skipped + save_failures
        processed += saved
        errors += batch_errors
        _log_dropped(
            "Distributed CLIP result",
            {
                "worker_skipped": worker_skipped,
                "save_fail": save_failures,
            },
            expected_dim,
        )

    result = dispatch_inference_sync(
        router, "clip", items,
        batch_size=batch_size, mode="parallel",
        worker_fn=worker_fn, result_fn=result_fn,
    )
    del result
    return processed, errors


def encode_local_batch(batch_items, encoder, preprocess_fn, expected_dim: int | None = None):
    """Encode images locally, return list of (file_id, vector) tuples."""
    results = []
    drop_counts: dict[str, int] = {}
    for fid, path in batch_items:
        try:
            preprocessed = preprocess_fn(path)
            if preprocessed.ndim == 4:
                preprocessed = preprocessed[0]
            vec = encoder.encode(preprocessed)
            reason = _vector_skip_reason(vec, expected_dim)
            if reason is None:
                results.append((fid, vec))
            else:
                drop_counts[reason] = drop_counts.get(reason, 0) + 1
        except Exception as exc:
            logger.debug("Local encode failed %d: %s", fid, exc)
            drop_counts["encode_error"] = drop_counts.get("encode_error", 0) + 1
    _log_dropped("Distributed CLIP local", drop_counts, expected_dim)
    return results


def _expected_vector_dim(encoder) -> int | None:
    global _warned_missing_output_dim
    output_dim = getattr(encoder, "output_dim", None)
    if isinstance(output_dim, int) and output_dim > 0:
        return output_dim
    if not _warned_missing_output_dim:
        logger.warning(
            "CLIP encoder %s has no valid output_dim; skipping vector dimension check",
            type(encoder).__name__,
        )
        _warned_missing_output_dim = True
    return None


def _is_valid_vector(vec, expected_dim: int | None) -> bool:
    return _vector_skip_reason(vec, expected_dim) is None


def _vector_skip_reason(vec, expected_dim: int | None) -> str | None:
    if vec is None:
        return "none"
    arr = np.asarray(vec)
    if arr.ndim != 1 or arr.size == 0:
        return "empty_or_not_1d"
    if expected_dim is not None and arr.shape[0] != expected_dim:
        return "dim_mismatch"
    return None


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
        logger.warning("Distributed CLIP dropped %d extra worker results", extra)
    return valid_results, worker_skipped


def _log_dropped(context: str, counts: dict[str, int], expected_dim: int | None) -> None:
    counts = {reason: count for reason, count in counts.items() if count}
    if not counts:
        return
    total = sum(counts.values())
    breakdown = ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))
    logger.warning("%s dropped %d items: %s, expected_dim=%s", context, total, breakdown, expected_dim)


def _encode_fallback(ids, arrays, encoder):
    ok_ids = []
    vecs = []
    failed = 0
    for idx, arr in enumerate(arrays):
        try:
            vecs.append(encoder.encode(arr[np.newaxis, ...]))
            ok_ids.append(ids[idx])
        except Exception:
            failed += 1
    return ok_ids, np.stack(vecs) if vecs else None, failed


def _save_with_retry(ids, vecs, save_fn: Callable) -> bool:
    for retry in range(3):
        try:
            save_fn(ids, vecs)
            return True
        except Exception as exc:
            if "locked" in str(exc).lower() and retry < 2:
                import time as _time

                _time.sleep(3.0 * (retry + 1))
            else:
                logger.error("Batch save failed: %s", exc)
                return False
    return False
