"""Maintenance helpers for post-scan finalization."""

from __future__ import annotations

import logging
import threading
import time

from core.event_bus import emit
from core.event_bus.event_types import SCAN_PROGRESS

logger = logging.getLogger(__name__)

_MAINT_LOCK = threading.Lock()
_LAST_MAINT_AT: dict[str, float] = {}
_MAINT_IN_FLIGHT: set[str] = set()
_MAINT_INTERVAL_SEC = {
    "normalize_tags": 600.0,
    "optimize_fts": 1800.0,
    "analyze": 1800.0,
    "monthly_stats": 600.0,
}


def _try_acquire_maintenance(kind: str) -> bool:
    interval = float(_MAINT_INTERVAL_SEC.get(kind, 0.0))
    now = time.monotonic()
    with _MAINT_LOCK:
        if kind in _MAINT_IN_FLIGHT:
            return False
        if interval <= 0:
            _MAINT_IN_FLIGHT.add(kind)
            return True
        last = _LAST_MAINT_AT.get(kind)
        if last is not None and now - last < interval:
            return False
        _MAINT_IN_FLIGHT.add(kind)
    return True


def _finish_maintenance(kind: str, success: bool) -> None:
    now = time.monotonic()
    with _MAINT_LOCK:
        _MAINT_IN_FLIGHT.discard(kind)
        if success:
            _LAST_MAINT_AT[kind] = now


def _post_progress(job_id: str, job_label: str, count: int, detail: str) -> None:
    emit(
        SCAN_PROGRESS,
        {"current": count, "total": count, "percent": 99, "job_id": job_id, "label": job_label, "detail": detail, "phase": "cleanup"},
        source="scan",
    )


def _run_db_refreshes() -> None:
    if _try_acquire_maintenance("analyze"):
        try:
            from core.services_core.db_api import get_db
            from core.services_core.db_write import submit_db_write_no_wait

            def _analyze() -> None:
                success = False
                try:
                    con = get_db()
                    for table in ("files", "file_tags", "templates"):
                        con.execute(f"ANALYZE {table}")
                    con.commit()
                    success = True
                except Exception as exc:
                    logger.debug("Analyze refresh skipped: %s", exc)
                finally:
                    _finish_maintenance("analyze", success)

            submit_db_write_no_wait(_analyze)
        except Exception:
            _finish_maintenance("analyze", False)
            return

    try:
        try:
            from core.schema_core.schema_constants import CURRENT_PARSER_VERSION
            from core.services_core.db_meta import refresh_file_stats_serialized

            refresh_file_stats_serialized(CURRENT_PARSER_VERSION)
        finally:
            from core.search_api.server_info import mark_stats_refresh_complete

            mark_stats_refresh_complete()
    except Exception as exc:
        logger.debug("db_meta refresh skipped: %s", exc)

    try:
        from core.search_api.file_meta_cache import file_meta_cache

        file_meta_cache.invalidate()
    except Exception:
        logger.debug("scan step failed", exc_info=True)

    try:
        from core.stats_api.stats_cache import invalidate_signature_cache

        invalidate_signature_cache()
    except Exception:
        logger.debug("scan step failed", exc_info=True)

    if _try_acquire_maintenance("monthly_stats"):
        try:
            def _refresh_monthly():
                success = False
                try:
                    from core.services_core.db_api import get_db as _get_db
                    from core.services_core.db_write import submit_db_write_no_wait
                    from core.stats_api.monthly_stats_materialize import refresh_monthly_stats

                    def _run_monthly() -> None:
                        nonlocal success
                        try:
                            refresh_monthly_stats(_get_db())
                            from core.stats_api.stats_cache import invalidate_signature_cache

                            invalidate_signature_cache()
                            success = True
                        except Exception as exc:
                            logger.debug("Monthly stats refresh skipped: %s", exc)
                        finally:
                            _finish_maintenance("monthly_stats", success)

                    submit_db_write_no_wait(_run_monthly)
                except Exception as exc:
                    logger.debug("Monthly stats refresh skipped: %s", exc)
                    _finish_maintenance("monthly_stats", False)

            threading.Thread(target=_refresh_monthly, name="monthly-stats-refresh", daemon=True).start()
        except Exception:
            _finish_maintenance("monthly_stats", False)
