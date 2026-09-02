import contextlib
import logging
import time
from threading import Condition, Lock, Thread

from core.helpers_core.helpers_text_path import is_archive_member
from core.scan_core.scanner import scan_batch, scan_one
from core.services_core.db_api import get_db
from core.services_core.db_write import submit_db_write

from .runtime_execute_helpers import (
    SLOW_ENTRY_WARN,
    collect_archive_batch,
    should_compute_hash,
)

logger = logging.getLogger(__name__)
_ERR_FLUSH_INTERVAL = 1.0
_ERR_BATCH_SIZE = 128
_ERR_MAX_PENDING = 2000
_err_pending: dict[tuple[str, str], str] = {}
_err_cv = Condition(Lock())
_err_worker_started = False


def is_archive_path(path_obj) -> bool:
    return isinstance(path_obj, str) and is_archive_member(str(path_obj))


def _record_scan_error_batch(items: list[tuple[str, str, str]]) -> None:
    from core.scan_core.scan_errors import record_scan_error

    con = get_db()
    for path, error_type, detail in items:
        record_scan_error(con, path, error_type, detail)
    con.commit()


def _error_worker_loop() -> None:
    while True:
        with _err_cv:
            if not _err_pending:
                _err_cv.wait()
            if not _err_pending:
                continue
            _err_cv.wait(timeout=_ERR_FLUSH_INTERVAL)
            keys = list(_err_pending.keys())[:_ERR_BATCH_SIZE]
            batch = []
            for key in keys:
                detail = _err_pending.pop(key, None)
                if detail is not None:
                    batch.append((key[0], key[1], detail))
        if not batch:
            continue
        with contextlib.suppress(Exception):
            submit_db_write(lambda _batch=batch: _record_scan_error_batch(_batch))


def _ensure_error_worker() -> None:
    global _err_worker_started
    with _err_cv:
        if _err_worker_started:
            return
        Thread(target=_error_worker_loop, daemon=True, name="scan-error-batch").start()
        _err_worker_started = True


def _queue_scan_error(path: str, error_type: str, detail: str) -> None:
    _ensure_error_worker()
    with _err_cv:
        key = (str(path), str(error_type))
        if key not in _err_pending and len(_err_pending) >= _ERR_MAX_PENDING:
            oldest_key = next(iter(_err_pending), None)
            if oldest_key is not None:
                _err_pending.pop(oldest_key, None)
        _err_pending[key] = str(detail)
        _err_cv.notify()


def process_archive_batch(
    file_queue,
    con,
    config,
    *,
    force: bool,
    compute_hash_explicit: bool,
    skip_backfill: bool,
    archive_cache,
    thumb_pipeline,
    added_ids: list,
    updated_ids: list,
) -> dict:
    arc, internal_paths, _full_paths = collect_archive_batch(file_queue)
    batch_size = len(internal_paths)
    batch_added = []
    entry_start = time.time()
    try:
        batch_results = scan_batch(
            con,
            arc,
            internal_paths,
            config,
            force=force,
            compute_hash=should_compute_hash(config, explicit=compute_hash_explicit),
            skip_backfill=skip_backfill,
            archive_cache=archive_cache,
        )
        backfilled = 0
        for result in batch_results:
            if result is None:
                continue
            action, file_id = result
            if action == "added":
                added_ids.append(file_id)
                batch_added.append(file_id)
            elif action == "backfilled":
                backfilled += 1
            else:
                updated_ids.append(file_id)
        if thumb_pipeline and batch_added:
            thumb_pipeline.enqueue(batch_added)
        return _archive_result(arc, batch_size, 0, backfilled, time.time() - entry_start)
    except Exception as exc:
        etype = type(exc).__name__
        logger.warning("scan_batch failed for %s: %s: %s", arc, etype, exc)
        with contextlib.suppress(Exception):
            _queue_scan_error(arc, "archive_scan", f"{etype}: {exc}")
        return _archive_result(arc, batch_size, batch_size, 0, time.time() - entry_start, str(exc))


def process_regular_file(
    p,
    con,
    config,
    *,
    force: bool,
    compute_hash_explicit: bool,
    skip_backfill: bool,
    thumb_pipeline,
    added_ids: list,
    updated_ids: list,
) -> dict:
    p_str = str(p)
    p_name = str(p.name) if hasattr(p, "name") else p_str
    entry_start = time.time()
    try:
        result = scan_one(
            con,
            p,
            config,
            force=force,
            compute_hash=should_compute_hash(config, explicit=compute_hash_explicit),
            skip_backfill=skip_backfill,
        )
        backfilled = 0
        if result is not None:
            action, file_id = result
            if action == "added":
                added_ids.append(file_id)
                if thumb_pipeline:
                    thumb_pipeline.enqueue([file_id])
            elif action == "backfilled":
                backfilled += 1
            else:
                updated_ids.append(file_id)
        return _file_result(p_name, 0, backfilled, time.time() - entry_start)
    except Exception as exc:
        etype = type(exc).__name__
        logger.warning("scan_one failed for %s: %s: %s", p_name, etype, exc)
        error_type = "timeout" if isinstance(exc, TimeoutError) else "scan"
        try:
            _queue_scan_error(p_str, error_type, f"{etype}: {exc}")
        except Exception:
            logger.debug("Failed to record scan error for %s", p_str)
        return _file_result(p_name, 1, 0, time.time() - entry_start, str(exc))


def _archive_result(path: str, batch_size: int, errors: int, backfilled: int, elapsed: float, error_message: str = "") -> dict:
    if elapsed > SLOW_ENTRY_WARN:
        logger.warning("Slow archive batch (%.1fs, %d entries): %s", elapsed, batch_size, path)
    arc_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return {
        "detail": f"{arc_name} ({batch_size} files)",
        "count_delta": batch_size,
        "errors": errors,
        "backfilled": backfilled,
        "error_message": error_message,
    }


def _file_result(name: str, errors: int, backfilled: int, elapsed: float, error_message: str = "") -> dict:
    if elapsed > SLOW_ENTRY_WARN:
        logger.warning("Slow scan entry (%.1fs): %s", elapsed, name)
    return {
        "detail": name,
        "count_delta": 1,
        "errors": errors,
        "backfilled": backfilled,
        "error_message": error_message,
    }

