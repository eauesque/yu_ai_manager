"""Finalize scan runtime side effects after the main scan loop completes."""

from __future__ import annotations

import logging
import threading
import time

from core.event_bus import emit
from core.event_bus.event_types import SCAN_COMPLETE, SCAN_DB_BUSY, SCAN_PROGRESS
from core.files_core.groups_index import invalidate_cache as invalidate_groups_cache
from core.query.tag_resolve_cache import path_match_probe_cache, tag_resolve_cache
from core.scan.runtime_finalize_maintenance import (
    _LAST_MAINT_AT,  # re-exported for tests (noqa: F401)
    _MAINT_IN_FLIGHT,  # re-exported for tests (noqa: F401)
    _finish_maintenance,
    _post_progress,
    _run_db_refreshes,
    _try_acquire_maintenance,
)

__all__ = [
    "_LAST_MAINT_AT",
    "_MAINT_IN_FLIGHT",
    "_post_progress",
    "_run_db_refreshes",
    "_try_acquire_maintenance",
    "_finish_maintenance",
    "finalize_scan_runtime",
]
from core.scan.runtime_post import (
    auto_register_scan_root,
    normalize_tags_after_scan,
    optimize_fts_tables,
    sync_deleted_files,
    wal_checkpoint,
)
from core.scan_core.scan_state import clear_scan_state
from core.search_api.count_cache import count_cache
from core.search_api.search_page_cache import search_page_cache

logger = logging.getLogger(__name__)

_ID_LIST_MAX = 5000


def _run_post_scan_maintenance_async(job_id: str, count: int) -> None:
    def _maintenance() -> None:
        try:
            emit(
                SCAN_PROGRESS,
                {"current": count, "total": count, "percent": 100, "job_id": job_id, "detail": "post-scan maintenance: normalize tags", "phase": "maintenance"},
                source="scan",
            )
            if _try_acquire_maintenance("normalize_tags"):
                success = False
                try:
                    normalize_tags_after_scan()
                    success = True
                finally:
                    _finish_maintenance("normalize_tags", success)
            else:
                logger.debug("Skip normalize_tags_after_scan (cooldown)")

            emit(
                SCAN_PROGRESS,
                {"current": count, "total": count, "percent": 100, "job_id": job_id, "detail": "post-scan maintenance: optimize fts", "phase": "maintenance"},
                source="scan",
            )
            if _try_acquire_maintenance("optimize_fts"):
                success = False
                try:
                    optimize_fts_tables()
                    success = True
                finally:
                    _finish_maintenance("optimize_fts", success)
            else:
                logger.debug("Skip optimize_fts_tables (cooldown)")

            emit(
                SCAN_PROGRESS,
                {"current": count, "total": count, "percent": 100, "job_id": job_id, "detail": "post-scan maintenance: wal checkpoint", "phase": "maintenance"},
                source="scan",
            )
            wal_checkpoint()
            _run_db_refreshes()
        except Exception as exc:
            logger.debug("Post-scan maintenance skipped: %s", exc)

    threading.Thread(target=_maintenance, name="scan-post-maintenance", daemon=True).start()


def finalize_scan_runtime(
    *,
    root_path: str,
    recursive: bool,
    job,
    own_job: bool,
    job_id: str,
    job_label: str,
    scan_started: float,
    count: int,
    enum_errors: list,
    loop_result: dict,
) -> None:
    job.update(phase="cleanup", message="削除済みファイルを検出中...")
    _post_progress(job_id, job_label, count, "削除済みファイルを検出中...")
    deleted_count, deleted_ids = sync_deleted_files(root_path)

    invalidate_groups_cache()
    tag_resolve_cache.invalidate()
    path_match_probe_cache.invalidate()
    count_cache.invalidate()
    search_page_cache.invalidate()

    from core.search_api.server_info import mark_stats_refresh_pending

    mark_stats_refresh_pending()

    errors = loop_result["errors"] + len(enum_errors)
    added_ids = loop_result.get("added_ids", [])
    updated_ids = loop_result.get("updated_ids", [])

    msg_parts = [f"{count}ファイルをスキャン完了"]
    if errors:
        msg_parts.append(f"{errors}件エラー")
    if deleted_count > 0:
        msg_parts.append(f"{deleted_count}件削除同期")
    summary = msg_parts[0] + ("（" + "、".join(msg_parts[1:]) + "）" if len(msg_parts) > 1 else "")

    if hasattr(job, "set_completion_data"):
        completion_data = {}
        if len(added_ids) <= _ID_LIST_MAX:
            completion_data["added_ids"] = added_ids
        if len(updated_ids) <= _ID_LIST_MAX:
            completion_data["updated_ids"] = updated_ids[:_ID_LIST_MAX]
        if len(deleted_ids) <= _ID_LIST_MAX:
            completion_data["deleted_ids"] = deleted_ids[:_ID_LIST_MAX]
        if completion_data:
            job.set_completion_data(**completion_data)

    if own_job:
        job.complete(summary)
    else:
        job.update(message=summary)

    event_data = {
        "count": count,
        "errors": errors,
        "deleted": deleted_count,
        "elapsed_seconds": round(time.time() - scan_started, 2),
        "job_id": job_id,
        "added_count": len(added_ids),
        "updated_count": len(updated_ids),
    }
    if len(added_ids) <= _ID_LIST_MAX:
        event_data["added_ids"] = added_ids
    if len(updated_ids) <= _ID_LIST_MAX:
        event_data["updated_ids"] = updated_ids
    if len(deleted_ids) <= _ID_LIST_MAX:
        event_data["deleted_ids"] = deleted_ids

    emit(SCAN_COMPLETE, event_data, source="scan")
    emit(SCAN_DB_BUSY, {"busy": False, "job_id": job_id}, source="scan")

    _run_post_scan_maintenance_async(job_id, count)
    clear_scan_state()
    auto_register_scan_root(root_path, recursive)

    try:
        from core.files_core.faststart_prescan import start_faststart_prescan

        start_faststart_prescan()
    except Exception:
        logger.debug("scan step failed", exc_info=True)
