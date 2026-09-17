"""Daemon batch worker for WD retag jobs."""

from __future__ import annotations

import logging
from typing import Any

from .engine_factory import get_engine
from .retag_db_ops import finalize_retag_batch, get_read_db, submit_db_write, write_retag_items
from .retag_targets import IN_LIST_CHUNK

logger = logging.getLogger(__name__)

_DB_WRITE_CHUNK = 100


def resolve_paths(con, file_ids: list[int]) -> dict[int, str]:
    if not file_ids:
        return {}
    out: dict[int, str] = {}
    for i in range(0, len(file_ids), IN_LIST_CHUNK):
        chunk = file_ids[i : i + IN_LIST_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        for row in rows:
            out[row["id"]] = row["path"]
    return out


def spawn_worker(
    *,
    job,
    file_ids,
    model_id,
    thresholds,
    batch_size,
    auto_set_active,
) -> None:
    import threading

    threading.Thread(
        target=batch_worker,
        kwargs={
            "job": job,
            "file_ids": file_ids,
            "model_id": model_id,
            "thresholds": thresholds,
            "batch_size": batch_size,
            "auto_set_active": auto_set_active,
        },
        daemon=True,
        name=f"retag-{job.job_id}",
    ).start()


def batch_worker(
    *,
    job,
    file_ids: list[int],
    model_id: str,
    thresholds: dict[str, float],
    batch_size: int,
    auto_set_active: bool = True,
) -> None:
    try:
        adapter = get_engine(_engine_config(model_id, thresholds))
    except Exception as exc:
        logger.exception("retag job model load failed")
        job.fail(error=str(exc))
        return
    try:
        _run_batches(job, adapter, file_ids, model_id, batch_size, auto_set_active)
    except Exception as exc:
        logger.exception("retag job %s crashed", job.job_id)
        job.fail(error=str(exc))


def _engine_config(model_id: str, thresholds: dict[str, float]) -> dict[str, Any]:
    return {
        "model": model_id,
        "engine_type": "onnx",
        "general_threshold": thresholds.get("general", 0.35),
        "character_threshold": thresholds.get("character", 0.85),
    }


def _run_batches(job, adapter, file_ids: list[int], model_id: str, batch_size: int, auto_set_active: bool) -> None:
    paths_by_id = resolve_paths(get_read_db(), file_ids)
    total = len(file_ids)
    processed = 0
    errors = 0
    job.update(phase="running", message=f"retag {model_id}")
    job.progress(current=0, total=total, detail=f"model={model_id}")
    pending_items: list = []
    for offset in range(0, total, batch_size):
        if job.cancelled:
            logger.info("retag job %s cancelled at offset %d", job.job_id, offset)
            break
        new_items, processed, errors = _process_chunk(
            job, adapter, file_ids[offset : offset + batch_size],
            paths_by_id, model_id, batch_size, processed, errors, total,
        )
        pending_items.extend(new_items)
        if len(pending_items) >= _DB_WRITE_CHUNK:
            submit_db_write(
                write_retag_items,
                items=pending_items,
                overwrite_same_model=True,
                auto_set_active=False,
                invalidate_count_cache=False,
            )
            pending_items.clear()
    if pending_items:
        submit_db_write(
            write_retag_items,
            items=pending_items,
            overwrite_same_model=True,
            auto_set_active=False,
            invalidate_count_cache=False,
        )
    if processed > 0:
        submit_db_write(
            finalize_retag_batch,
            model_id=model_id,
            auto_set_active=auto_set_active,
            invalidate_count_cache=True,
        )
    if job.cancelled:
        job.complete_cancelled(message=f"cancelled: {processed}/{total} processed, {errors} errors")
    else:
        job.complete(message=f"done: {processed}/{total} processed, {errors} errors")


def _process_chunk(
    job,
    adapter,
    chunk_ids: list[int],
    paths_by_id: dict[int, str],
    model_id: str,
    batch_size: int,
    processed: int,
    errors: int,
    total: int,
) -> tuple[list, int, int]:
    aligned_pairs = [(fid, paths_by_id[fid]) for fid in chunk_ids if fid in paths_by_id]
    errors += len(chunk_ids) - len(aligned_pairs)
    if not aligned_pairs:
        job.progress(current=processed, total=total, detail=f"model={model_id}, errors={errors}")
        return [], processed, errors
    aligned_ids = [pair[0] for pair in aligned_pairs]
    results = adapter.tag_images_batch([pair[1] for pair in aligned_pairs], batch_size=batch_size)
    if len(results) != len(aligned_ids):
        logger.warning("adapter %s returned %d results for %d paths", model_id, len(results), len(aligned_ids))
        errors += abs(len(aligned_ids) - len(results))
    items = [(fid, model_id, result) for fid, result in zip(aligned_ids, results, strict=False) if result is not None]
    errors += len(aligned_ids) - len(items)
    processed += len(items)
    job.progress(current=processed, total=total, detail=f"model={model_id}, errors={errors}")
    return items, processed, errors
