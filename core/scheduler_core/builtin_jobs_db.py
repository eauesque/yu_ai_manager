"""Built-in scheduled jobs -- database and maintenance operations.

Contains db_vacuum, db_integrity_check, thumbnail_cleanup,
thumbnail_cleanup_pressure, prune_unused_tags, refresh_monthly_stats,
rebuild_groups_index, and db_backup.
"""

import logging
import os
import time

logger = logging.getLogger(__name__)


def _with_db_cleanup(func):
    """Decorator: ensure thread-local DB connections are closed after job."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            from core.services_core.db_state import close_thread_connections
            close_thread_connections()
    wrapper.__name__ = func.__name__
    wrapper.__qualname__ = func.__qualname__
    return wrapper


def _db_vacuum_write() -> None:
    from core.services_core.db_state import get_db
    db = get_db()
    # VACUUM cannot run inside an implicit transaction; commit any pending
    # state on this writer-thread connection first.
    db.commit()
    db.execute("VACUUM")


@_with_db_cleanup
def db_vacuum() -> str:
    """Run VACUUM on the SQLite database to reclaim space."""
    from core.services_core.db_write import submit_db_write
    start = time.monotonic()
    submit_db_write(_db_vacuum_write)
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info("[SCHEDULER] db_vacuum completed in %dms", elapsed)
    return f"VACUUM completed in {elapsed}ms"


@_with_db_cleanup
def db_integrity_check() -> str:
    """Run a lightweight PRAGMA quick_check on the database."""
    from core.services_core.db_state import get_readonly_db
    db = get_readonly_db()
    start = time.monotonic()
    rows = db.execute("PRAGMA quick_check").fetchall()
    elapsed = int((time.monotonic() - start) * 1000)
    result = rows[0][0] if rows else "unknown"
    if result == "ok":
        logger.info("[SCHEDULER] db_integrity_check: ok (%dms)", elapsed)
    else:
        logger.warning("[SCHEDULER] db_integrity_check: %s (%dms)", result, elapsed)
    return f"quick_check: {result} ({elapsed}ms)"


@_with_db_cleanup
def thumbnail_cleanup() -> str:
    """Remove expired thumbnail cache files."""
    from core.services_core.thumbnail_cache_cleanup import cleanup_thumbnail_cache
    start = time.monotonic()
    removed = cleanup_thumbnail_cache()
    elapsed = int((time.monotonic() - start) * 1000)
    count = removed if isinstance(removed, int) else 0
    logger.info("[SCHEDULER] thumbnail_cleanup: removed %d files (%dms)", count, elapsed)
    return f"thumbnail_cleanup: removed {count} files ({elapsed}ms)"


@_with_db_cleanup
def thumbnail_cleanup_pressure() -> str:
    """Run cleanup only if cache is near capacity (>90%). Lightweight check."""
    from core.services_core.thumbnail_cache_cleanup import check_cache_pressure, cleanup_thumbnail_cache
    if not check_cache_pressure():
        return "thumbnail_cleanup_pressure: cache within budget, skipped"
    start = time.monotonic()
    removed = cleanup_thumbnail_cache()
    elapsed = int((time.monotonic() - start) * 1000)
    count = removed if isinstance(removed, int) else 0
    logger.info("[SCHEDULER] thumbnail_cleanup_pressure: removed %d files (%dms)", count, elapsed)
    return f"thumbnail_cleanup_pressure: removed {count} files ({elapsed}ms)"


@_with_db_cleanup
def thumbnail_integrity_check() -> str:
    """Detect and evict thumbnails whose source file is newer (stale)."""
    from core.services_core.thumbnail_integrity import check_thumbnail_integrity
    start = time.monotonic()
    result = check_thumbnail_integrity()
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(
        "[SCHEDULER] thumbnail_integrity_check: checked=%d stale=%d orphan=%d (%dms)",
        result["checked"], result["stale_evicted"], result["missing_source_evicted"], elapsed,
    )
    return (
        f"thumbnail_integrity_check: checked={result['checked']} "
        f"stale={result['stale_evicted']} orphan={result['missing_source_evicted']} "
        f"({elapsed}ms)"
    )


def _prune_unused_tags_write() -> int:
    from core.cleanup_core.cleanup_files import cleanup_prune_unused_tags
    from core.services_core.db_state import get_db

    db = get_db()
    count = cleanup_prune_unused_tags(db, dry_run=False)
    db.commit()
    return count


@_with_db_cleanup
def prune_unused_tags() -> str:
    """Remove orphaned tag records that have no associated files."""
    from core.services_core.db_write import submit_db_write
    start = time.monotonic()
    count = submit_db_write(_prune_unused_tags_write)
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info("[SCHEDULER] prune_unused_tags: removed %d tags (%dms)", count, elapsed)
    return f"prune_unused_tags: removed {count} tags ({elapsed}ms)"


def _refresh_monthly_stats_write() -> int:
    from core.services_core.db_state import get_db
    from core.stats_api.monthly_stats_materialize import (
        refresh_monthly_stats as _refresh,
    )

    db = get_db()
    return _refresh(db)


@_with_db_cleanup
def refresh_monthly_stats() -> str:
    """Refresh pre-calculated monthly statistics cache."""
    from core.services_core.db_write import submit_db_write
    start = time.monotonic()
    months = submit_db_write(_refresh_monthly_stats_write)
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info("[SCHEDULER] refresh_monthly_stats: %d months updated (%dms)", months, elapsed)
    return f"refresh_monthly_stats: {months} months updated ({elapsed}ms)"


@_with_db_cleanup
def rebuild_groups_index() -> str:
    """Rebuild folder/archive grouping index cache."""
    from core.tools_api.ops import rebuild_groups

    start = time.monotonic()
    result = rebuild_groups()
    elapsed = int((time.monotonic() - start) * 1000)
    folders = result.get("folders", 0)
    zips = result.get("zips", 0)
    logger.info(
        "[SCHEDULER] rebuild_groups_index: %d folders, %d zips (%dms)",
        folders, zips, elapsed,
    )
    return f"rebuild_groups_index: {folders} folders, {zips} zips ({elapsed}ms)"


def _db_analyze_write() -> None:
    from core.services_core.db_state import get_db
    db = get_db()
    db.execute("ANALYZE")
    db.commit()


@_with_db_cleanup
def db_analyze() -> str:
    """Run ANALYZE to update query planner statistics.

    Critical for 10GB+ databases where stale statistics cause the planner
    to pick wrong indexes (e.g. full-table scan instead of mtime index).
    """
    from core.services_core.db_write import submit_db_write
    start = time.monotonic()
    submit_db_write(_db_analyze_write)
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info("[SCHEDULER] db_analyze completed in %dms", elapsed)
    return f"ANALYZE completed in {elapsed}ms"


def db_backup() -> str:
    """Create a scheduled database backup."""
    import importlib

    spec_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "extensions", "builtin-backup",
        "core_impl", "__init__.py",
    )
    spec = importlib.util.spec_from_file_location(
        "backup_core_impl", spec_path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    start = time.monotonic()
    result = mod.create_backup(reason="scheduled")
    elapsed = int((time.monotonic() - start) * 1000)

    if "error" in result:
        msg = f"db_backup failed: {result['error']} ({elapsed}ms)"
        logger.warning("[SCHEDULER] %s", msg)
        raise RuntimeError(msg)

    filename = result.get("filename", "?")
    size = result.get("size_bytes", 0)
    logger.info(
        "[SCHEDULER] db_backup: %s (%d bytes, %dms)", filename, size, elapsed,
    )
    return f"db_backup: {filename} ({size} bytes, {elapsed}ms)"


def _db_compress_old_raw_responses_write() -> int:
    from core.services_core.db_state import get_db
    db = get_db()
    result = db.execute("""
        UPDATE analysis
        SET raw_response = NULL
        WHERE analyzed_at < strftime('%s','now','-60 days')
          AND raw_response IS NOT NULL
    """)
    db.commit()
    return result.rowcount


@_with_db_cleanup
def db_compress_old_raw_responses() -> str:
    """Nullify analysis.raw_response older than 60 days (storage reduction).

    raw_response is VLM-generated raw text that can be regenerated,
    so periodic deletion is safe. Tags, scores, and description are preserved.
    """
    from core.services_core.db_write import submit_db_write
    start = time.monotonic()
    count = submit_db_write(_db_compress_old_raw_responses_write)
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(
        "[SCHEDULER] db_compress_old_raw_responses: %d rows nullified (%dms)",
        count, elapsed,
    )
    return f"db_compress_old_raw_responses: {count} rows nullified ({elapsed}ms)"


def _db_prune_old_webhook_deliveries_write() -> int:
    from core.services_core.db_state import get_db
    db = get_db()
    result = db.execute("""
        DELETE FROM webhook_deliveries
        WHERE delivered_at < strftime('%s','now','-90 days')
    """)
    db.commit()
    return result.rowcount


@_with_db_cleanup
def db_prune_old_webhook_deliveries() -> str:
    """Delete webhook_deliveries older than 90 days."""
    from core.services_core.db_write import submit_db_write
    start = time.monotonic()
    count = submit_db_write(_db_prune_old_webhook_deliveries_write)
    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(
        "[SCHEDULER] db_prune_old_webhook_deliveries: %d deleted (%dms)",
        count, elapsed,
    )
    return f"db_prune_old_webhook_deliveries: {count} deleted ({elapsed}ms)"
