"""Batch worker helpers for Speech-to-Text transcription."""

import logging
import time

logger = logging.getLogger(__name__)

from .s2t_batch_distributed import has_remote_workers as _has_remote_workers
from .s2t_batch_distributed import run_distributed_batch as _run_distributed_batch
from .s2t_batch_local import (
    transcribe_single,
)

_IN_CHUNK_SIZE = 500


def run_batch(file_ids, language, backend_pref, model_size, distributed=False):
    """Background batch transcription worker."""
    from importlib import import_module

    from core.event_bus import emit
    from core.files_core.video_audio import extract_audio_wav
    from core.services_core.db_api import get_readonly_db

    from .core_impl.backend_registry import get_backend

    ann_store = import_module("extensions.builtin_annotations.core_impl.store")
    upsert_annotations_batch_commit = ann_store.upsert_annotations_batch_commit

    total = len(file_ids)
    emit("s2t.batch_start", {"total": total}, source="s2t")

    con = get_readonly_db()
    paths_map = _get_active_paths(con, file_ids)

    backend = _init_backend_or_emit(get_backend, backend_pref, model_size, distributed, total)
    if backend is None and not distributed:
        return

    started_at = time.time()
    if distributed and _has_remote_workers():
        result = _run_distributed_batch(
            file_ids,
            paths_map,
            backend,
            language,
            extract_audio_wav,
            upsert_annotations_batch_commit,
            started_at,
            emit_progress,
        )
        if result is not None:
            _emit_batch_complete(result["processed"], result["errors"], total, started_at)
            return

    processed = 0
    errors = 0
    for file_id in file_ids:
        done, failed = transcribe_single(
            file_id,
            paths_map,
            backend,
            language,
            extract_audio_wav,
            upsert_annotations_batch_commit,
        )
        processed += done
        errors += failed
        emit_progress(processed, errors, total, started_at)

    _emit_batch_complete(processed, errors, total, started_at)


def _get_active_paths(con, file_ids) -> dict[int, str]:
    paths_map: dict[int, str] = {}
    for index in range(0, len(file_ids), _IN_CHUNK_SIZE):
        chunk = file_ids[index : index + _IN_CHUNK_SIZE]
        if not chunk:
            continue
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
            chunk,
        )
        paths_map.update({row[0]: row[1] for row in rows})
    return paths_map


def _init_backend_or_emit(get_backend, backend_pref, model_size, distributed, total):
    from core.event_bus import emit

    try:
        return get_backend(backend_pref, model_size)
    except Exception as exc:
        if distributed:
            logger.warning("Local S2T backend unavailable (%s), using remote-only", exc)
            return None
        emit(
            "s2t.batch_complete",
            {
                "reason": f"Backend init failed: {exc}",
                "processed": 0,
                "errors": total,
                "total": total,
                "elapsed_seconds": 0,
            },
            source="s2t",
        )
        return None


def emit_progress(processed, errors, total, started_at):
    """Emit SSE progress event."""
    from core.event_bus import emit

    elapsed = round(time.time() - started_at, 1)
    pct = round((processed + errors) / total * 100, 1)
    emit(
        "s2t.batch_progress",
        {
            "processed": processed,
            "total": total,
            "errors": errors,
            "percent": pct,
            "elapsed": elapsed,
        },
        source="s2t",
    )


def _emit_batch_complete(processed, errors, total, started_at):
    from core.event_bus import emit

    elapsed = round(time.time() - started_at, 1)
    emit(
        "s2t.batch_complete",
        {
            "reason": "complete",
            "processed": processed,
            "errors": errors,
            "total": total,
            "elapsed_seconds": elapsed,
        },
        source="s2t",
    )
