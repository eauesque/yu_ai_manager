"""Retag job entry points (single + batch with 3 scopes)."""

from __future__ import annotations

import time
from typing import Any

from core.services_core.wd_dict_resolver import resolve_model_id_readonly

from .engine_factory import get_engine
from .registry import TaggerRegistry
from .retag_db_ops import (
    finalize_retag_batch as _finalize_retag_batch,
)
from .retag_db_ops import (
    get_read_db as _get_read_db,
)
from .retag_db_ops import (
    submit_db_write as _submit_db_write,
)
from .retag_db_ops import (
    write_retag_items as _write_retag_items,
)
from .retag_targets import IN_LIST_CHUNK as _IN_LIST_CHUNK


def _normalize_scan_root(scan_root: str) -> str:
    return scan_root.rstrip("/\\")


def _like_escape(value: str) -> str:
    return value.replace("~", "~~").replace("%", "~%").replace("_", "~_")


def _scan_root_like_patterns(scan_root: str) -> tuple[str, str]:
    root = _normalize_scan_root(scan_root)
    fwd = _like_escape(root.replace("\\", "/").rstrip("/"))
    bck = _like_escape(root.replace("/", "\\").rstrip("\\"))
    return f"{fwd}/%", f"{bck}\\%"


def _canonicalize_model_id(model_id: str) -> str:
    profile = TaggerRegistry.get().resolve_any(model_id)
    if profile is None:
        raise LookupError(f"unknown model_id={model_id!r}; not a known profile id or HF repo")
    return profile.id


def _get_engine_for_config(config: dict[str, Any]):
    return get_engine(config)


def _resolve_file_path(con, file_id: int) -> str:
    row = con.execute(
        "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
        (file_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"file_id={file_id} not found or deleted")
    return row["path"] if hasattr(row, "keys") else row[0]


def start_single(
    file_id: int,
    model_id: str,
    thresholds: dict[str, float],
    *,
    overwrite_same_model: bool = True,
    auto_set_active: bool = True,
) -> dict[str, Any]:
    """Run retagging on one file synchronously."""
    t0 = time.monotonic()
    model_id = _canonicalize_model_id(model_id)
    file_path = _resolve_file_path(_get_read_db(), file_id)
    result = _get_engine_for_config(_engine_config(model_id, thresholds)).tag_image(file_path)
    inserted = _submit_db_write(
        _write_retag_items,
        items=[(file_id, model_id, result)],
        overwrite_same_model=overwrite_same_model,
        auto_set_active=auto_set_active,
    )
    return {
        "file_id": file_id,
        "model_id": model_id,
        "tags": [
            {"tag": tag.tag, "confidence": tag.confidence, "category": tag.category}
            for tag in result.tags
        ],
        "rating": getattr(result, "rating", ""),
        "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "inserted": inserted,
    }


def start_batch(
    *,
    scope: str,
    model_id: str,
    thresholds: dict[str, float],
    file_ids: list[int] | None = None,
    scan_root: str = "",
    force: bool = False,
    batch_size: int = 8,
    limit: int = 0,
    search_fn=None,
    query_params: dict[str, Any] | None = None,
    auto_set_active: bool = True,
) -> dict[str, Any]:
    """Start a non-blocking batch retag job."""
    from core.jobs_core.jobs import job_manager

    if batch_size < 1 or batch_size > 64:
        raise ValueError(f"batch_size must be in [1, 64], got {batch_size}")
    model_id = _canonicalize_model_id(model_id)
    target_spec: dict[str, Any] | None = None
    targets: list[int] | None
    if scope == "backfill":
        total = _count_backfill_targets(
            _get_read_db(),
            model_id=model_id,
            scan_root=scan_root,
            force=force,
            limit=limit,
        )
        if total <= 0:
            return {"started": False, "reason": "no_targets", "scope": scope}
        targets = None
        target_spec = {
            "scope": "backfill",
            "model_id": model_id,
            "scan_root": scan_root,
            "force": force,
            "limit": limit,
            "total": total,
        }
    else:
        targets = _enumerate_targets(
            scope=scope,
            model_id=model_id,
            file_ids=file_ids,
            scan_root=scan_root,
            force=force,
            limit=limit,
            search_fn=search_fn,
            query_params=query_params,
        )
        if not targets:
            return {"started": False, "reason": "no_targets", "scope": scope}
    try:
        job = job_manager.start("wd_tagger", "WD-Tagger retag")
    except ValueError:
        return {"error": "WD-Tagger retag job already running", "code": "job_running"}
    _spawn_worker(
        job=job,
        file_ids=targets,
        target_spec=target_spec,
        model_id=model_id,
        thresholds=thresholds,
        batch_size=batch_size,
        auto_set_active=auto_set_active,
    )
    return {"started": True, "job_id": job.job_id}


def _engine_config(model_id: str, thresholds: dict[str, float]) -> dict[str, Any]:
    return {
        "model": model_id,
        "engine_type": "onnx",
        "general_threshold": thresholds.get("general", 0.35),
        "character_threshold": thresholds.get("character", 0.85),
    }


def _enumerate_targets(
    scope: str,
    *,
    model_id: str,
    file_ids: list[int] | None = None,
    scan_root: str = "",
    force: bool = False,
    limit: int = 0,
    search_fn=None,
    query_params: dict[str, Any] | None = None,
) -> list[int]:
    con = _get_read_db()
    if scope == "batch":
        active = _filter_active_in_order(con, file_ids or [])
        return active[:limit] if limit > 0 else active
    if scope == "backfill":
        scan_root = _normalize_scan_root(scan_root)
        sql = "SELECT id FROM files WHERE is_deleted = 0"
        params: list[Any] = []
        if scan_root:
            sql += " AND (path LIKE ? ESCAPE '~' OR path LIKE ? ESCAPE '~')"
            params.extend(_scan_root_like_patterns(scan_root))
        if not force:
            mid = resolve_model_id_readonly(con, model_id)
            if mid is None:
                mid = -1
            sql += (
                " AND NOT EXISTS (SELECT 1 FROM file_wd_tags fwt "
                "WHERE fwt.file_id = files.id AND fwt.model_id = ?)"
            )
            params.append(mid)
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        return [row[0] for row in con.execute(sql, params)]
    if scope == "query":
        if search_fn is None:
            raise ValueError("scope=query requires search_fn")
        active = _filter_active_in_order(con, list(search_fn(query_params or {})))
        return active[:limit] if limit > 0 else active
    raise ValueError(f"unknown scope={scope!r}")


def _backfill_where(
    *,
    model_id: str,
    scan_root: str,
    force: bool,
    after_id: int | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["is_deleted = 0"]
    params: list[Any] = []
    if after_id is not None:
        clauses.append("id > ?")
        params.append(after_id)
    scan_root = _normalize_scan_root(scan_root)
    if scan_root:
        clauses.append("(path LIKE ? ESCAPE '~' OR path LIKE ? ESCAPE '~')")
        params.extend(_scan_root_like_patterns(scan_root))
    if not force:
        mid = resolve_model_id_readonly(_get_read_db(), model_id)
        if mid is None:
            mid = -1
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM file_wd_tags fwt "
            "WHERE fwt.file_id = files.id AND fwt.model_id = ?)"
        )
        params.append(mid)
    return " AND ".join(clauses), params


def _count_backfill_targets(
    con,
    *,
    model_id: str,
    scan_root: str,
    force: bool,
    limit: int,
) -> int:
    where_sql, params = _backfill_where(
        model_id=model_id,
        scan_root=scan_root,
        force=force,
    )
    row = con.execute(
        f"SELECT COUNT(*) FROM files WHERE {where_sql}",
        params,
    ).fetchone()
    count = int(row[0]) if row else 0
    return min(count, limit) if limit > 0 else count


def _iter_backfill_target_batches(
    *,
    model_id: str,
    scan_root: str,
    force: bool,
    limit: int,
    page_size: int,
):
    yielded = 0
    last_id = 0
    while True:
        if limit > 0 and yielded >= limit:
            return
        batch_limit = page_size
        if limit > 0:
            batch_limit = min(batch_limit, limit - yielded)
        where_sql, params = _backfill_where(
            model_id=model_id,
            scan_root=scan_root,
            force=force,
            after_id=last_id,
        )
        rows = list(_get_read_db().execute(
            f"SELECT id FROM files WHERE {where_sql} ORDER BY id LIMIT ?",
            [*params, batch_limit],
        ))
        if not rows:
            return
        ids = [row[0] for row in rows]
        yielded += len(ids)
        last_id = ids[-1]
        yield ids


def _filter_active_in_order(con, file_ids: list[int]) -> list[int]:
    active: set[int] = set()
    for i in range(0, len(file_ids), _IN_LIST_CHUNK):
        chunk = file_ids[i : i + _IN_LIST_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        active.update(row[0] for row in rows)
    return [fid for fid in file_ids if fid in active]


def _resolve_paths(con, file_ids: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for i in range(0, len(file_ids), _IN_LIST_CHUNK):
        chunk = file_ids[i : i + _IN_LIST_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        for row in rows:
            out[row["id"]] = row["path"]
    return out


def _spawn_worker(
    *,
    job,
    file_ids,
    target_spec,
    model_id,
    thresholds,
    batch_size,
    auto_set_active,
) -> None:
    import threading

    threading.Thread(
        target=_batch_worker,
        kwargs={
            "job": job,
            "file_ids": file_ids,
            "target_spec": target_spec,
            "model_id": model_id,
            "thresholds": thresholds,
            "batch_size": batch_size,
            "auto_set_active": auto_set_active,
        },
        daemon=True,
        name=f"retag-{job.job_id}",
    ).start()


def _batch_worker(
    *,
    job,
    file_ids: list[int] | None = None,
    target_spec: dict[str, Any] | None = None,
    model_id: str,
    thresholds: dict[str, float],
    batch_size: int,
    auto_set_active: bool = True,
) -> None:
    try:
        adapter = _get_engine_for_config(_engine_config(model_id, thresholds))
    except Exception as exc:
        job.fail(error=str(exc))
        return
    try:
        if file_ids is None and target_spec is None:
            raise ValueError("file_ids or target_spec is required")
        processed = 0
        errors = 0
        total = (
            int(target_spec.get("total", 0))
            if target_spec is not None
            else len(file_ids or [])
        )
        job.update(phase="running", message=f"retag {model_id}")
        job.progress(current=0, total=total, detail=f"model={model_id}")
        if target_spec is not None and target_spec.get("scope") == "backfill":
            id_batches = _iter_backfill_target_batches(
                model_id=model_id,
                scan_root=str(target_spec.get("scan_root", "")),
                force=bool(target_spec.get("force", False)),
                limit=int(target_spec.get("limit", 0)),
                page_size=max(batch_size * 8, 128),
            )
        else:
            static_file_ids = file_ids or []
            id_batches = (
                static_file_ids[offset : offset + batch_size]
                for offset in range(0, len(static_file_ids), batch_size)
            )
        for chunk_ids in id_batches:
            if job.cancelled:
                break
            paths_by_id = _resolve_paths(_get_read_db(), chunk_ids)
            pairs = [(fid, paths_by_id[fid]) for fid in chunk_ids if fid in paths_by_id]
            errors += len(chunk_ids) - len(pairs)
            if not pairs:
                job.progress(current=processed, total=total, detail=f"model={model_id}, errors={errors}")
                continue
            for pair_offset in range(0, len(pairs), batch_size):
                if job.cancelled:
                    break
                batch_pairs = pairs[pair_offset : pair_offset + batch_size]
                batch_ids = [pair[0] for pair in batch_pairs]
                results = adapter.tag_images_batch(
                    [pair[1] for pair in batch_pairs],
                    batch_size=batch_size,
                )
                errors += abs(len(batch_ids) - len(results))
                items = [
                    (fid, model_id, result)
                    for fid, result in zip(batch_ids, results, strict=False)
                    if result is not None
                ]
                errors += len(batch_ids) - len(items)
                if items:
                    _submit_db_write(
                        _write_retag_items,
                        items=items,
                        overwrite_same_model=True,
                        auto_set_active=False,
                        invalidate_count_cache=False,
                    )
                    processed += len(items)
            job.progress(current=processed, total=total, detail=f"model={model_id}, errors={errors}")
        if processed > 0:
            _submit_db_write(
                _finalize_retag_batch,
                model_id=model_id,
                auto_set_active=auto_set_active,
                invalidate_count_cache=True,
            )
        if job.cancelled:
            job.complete_cancelled(message=f"cancelled: {processed}/{total} processed, {errors} errors")
        else:
            job.complete(message=f"done: {processed}/{total} processed, {errors} errors")
    except Exception as exc:
        job.fail(error=str(exc))
