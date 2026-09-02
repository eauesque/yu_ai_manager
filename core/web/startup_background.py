"""Background startup task definitions for the web runtime."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError

from core.services_core.db_api import set_boot_ready
from core.services_core.thumbnail_cache_cleanup import cleanup_thumbnail_cache
from core.web.startup_background_hailo_judge import startup_hailo_auto_reboot_judge
from core.web.startup_mode import BackgroundTaskDef

logger = logging.getLogger(__name__)

POST_V81_VACUUM_ANALYZE_DONE_KEY = "post_v81_vacuum_analyze_done"
POST_V82_VACUUM_ANALYZE_DONE_KEY = "post_v82_vacuum_analyze_done"
POST_MIGRATION_VACUUM_ANALYZE_MAX_ATTEMPTS = 3
POST_MIGRATION_VACUUM_ANALYZE_RETRY_BASE_SECONDS = 2.0
# Backward-compatible names used by existing tests.
POST_V81_VACUUM_ANALYZE_MAX_ATTEMPTS = POST_MIGRATION_VACUUM_ANALYZE_MAX_ATTEMPTS
POST_V81_VACUUM_ANALYZE_RETRY_BASE_SECONDS = (
    POST_MIGRATION_VACUUM_ANALYZE_RETRY_BASE_SECONDS
)

# Completion barriers for startup tasks that hold the write lock through
# their own raw sqlite3 connection (bypassing the writer thread). Tasks
# that route writes through submit_db_write must wait for these to drop
# before issuing their first write, otherwise the writer thread blocks
# on busy_timeout=10000ms and aborts. See CHANGELOG v4.192.5 (A) / .6 (B).
_ANALYZE_DONE = threading.Event()
_FILE_META_CACHE_DONE = threading.Event()

# Map task names to their completion events so runtime_runner can pre-set
# them when the task is skipped (mode mismatch or env-disable). Without
# this, dependent tasks would block on .wait() for the full timeout.
_STARTUP_COMPLETION_EVENTS = {
    "analyze": _ANALYZE_DONE,
    "file_meta_cache": _FILE_META_CACHE_DONE,
}


def mark_startup_task_skipped(name: str) -> None:
    """Mark a startup task as 'done' from the dependents' point of view.

    Called by the runner when a task is filtered out by mode/env so that
    downstream tasks waiting on its completion event proceed immediately.
    """
    ev = _STARTUP_COMPLETION_EVENTS.get(name)
    if ev is not None:
        ev.set()


def wait_for_db_writers(timeout: float = 90.0) -> None:
    """Block until startup tasks that hold a raw-connection write lock finish.

    Extension DB migrations (ALTER TABLE etc.) need the write lock and must not
    run concurrently with analyze/file_meta_cache which bypass the writer thread.
    Same barrier pattern used by _startup_tag_normalize_backfill.
    """
    _ANALYZE_DONE.wait(timeout=timeout)
    _FILE_META_CACHE_DONE.wait(timeout=timeout)


def _startup_thumb_cleanup() -> None:
    cleanup_thumbnail_cache()


def _startup_analyze() -> None:
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _sqlite3
    from core.services_core.db_state import get_db_path

    try:
        con = _sqlite3.connect(str(get_db_path()), timeout=30.0)
        _apply_key(con)
        for table in ("files", "file_tags", "templates"):
            con.execute(f"ANALYZE {table}")
        con.commit()
        con.close()
    except Exception:
        logger.warning("web startup step failed", exc_info=True)
    finally:
        _ANALYZE_DONE.set()


def _startup_file_meta_cache() -> None:
    from core.search_api.file_meta_cache import file_meta_cache
    from core.services_core.db_api import get_startup_status, set_startup_status
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _sqlite3
    from core.services_core.db_state import get_db_path

    # Expose stage so the booting banner can show "Initializing file cache..."
    existing = get_startup_status()
    set_startup_status({
        **(existing or {}),
        "stage": "file_cache",
        "kind": (existing or {}).get("kind", "startup"),
    })
    try:
        con = _sqlite3.connect(str(get_db_path()), timeout=30.0)
        _apply_key(con)
        con.row_factory = _sqlite3.Row
        file_meta_cache.ensure_built(con)
        con.close()
    except Exception:
        logger.warning("web startup step failed", exc_info=True)
    finally:
        _FILE_META_CACHE_DONE.set()
        set_boot_ready()

def _startup_stats_warmup() -> None:
    from core.stats_api.stats_cache import warmup_stats_cache

    warmup_stats_cache()


def _startup_llm_router_refresh() -> None:
    from core.web.runtime_llm_router import start_llm_router_refresh_loop
    start_llm_router_refresh_loop()


def _startup_wd_tagger_config_migrate_v2() -> None:
    """Run wd_tagger config v1->v2 migration if needed (spec § 8.2).

    Idempotent — exits early when already migrated. Failure is caught
    so it never blocks startup; the migration's own _migration_attempts
    counter handles retry-with-abort logic across reboots.
    """
    try:
        from extensions.builtin_wd_tagger.core_impl import config_ops
        result = config_ops.migrate_v1_to_v2()
        if result.get("aborted"):
            import logging
            logging.getLogger(__name__).warning(
                "wd_tagger config migration aborted: %s",
                result.get("reason"),
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "wd_tagger config migration v1->v2 failed; "
            "will retry on next boot"
        )


def _startup_tag_normalize_backfill() -> None:
    """Backfill legacy v71-v80 file_wd_tags.tag_name_normalized rows."""
    try:
        from core.schema_core.schema_migrate_version import get_schema_version
        from core.services_core.db_state import get_readonly_db

        if get_schema_version(get_readonly_db()) >= 81:
            return

        from core.services_core import kv_state
        from core.services_core.app_runtime_state import get_config
        from extensions.builtin_wd_tagger.core_impl.tag_normalize_backfill import (
            BACKFILL_MARKER_KEY,
            backfill_tag_normalized,
        )

        # Wait for parallel startup tasks that hold the raw-connection write
        # lock to finish before issuing the first writer-thread write. The
        # writer thread otherwise hits busy_timeout (10s) on its very first
        # marker INSERT. v4.192.5 (A) made the marker write fault-tolerant;
        # this barrier (B) avoids the 10s wait entirely on the common path.
        # 90s ceiling = generous upper bound; if either task is still running
        # past that we proceed anyway and let A's fault-tolerance handle it.
        _ANALYZE_DONE.wait(timeout=90.0)
        _FILE_META_CACHE_DONE.wait(timeout=90.0)

        marker = kv_state.get(BACKFILL_MARKER_KEY)
        if marker in ("completed", "disabled"):
            return

        cfg = (get_config() or {}).get("wd_tagger") or {}
        backfill_tag_normalized(
            batch_size=int(cfg.get("backfill_batch_size", 200)),
            sleep_ms=int(cfg.get("backfill_sleep_ms", 200)),
        )
    except Exception:
        # Backfill failure must not block startup; the task is idempotent
        # and will be retried on the next boot.
        import logging
        logging.getLogger(__name__).exception(
            "tag_normalize backfill failed; will retry on next boot"
        )


def _wait_for_startup_idle(timeout: float = 300.0, poll_interval: float = 1.0) -> None:
    from core.services_core.db_api import is_boot_ready

    deadline = time.monotonic() + timeout
    while not is_boot_ready() and time.monotonic() < deadline:
        time.sleep(poll_interval)
    wait_for_db_writers()


def _should_run_post_migration_vacuum_analyze(
    *,
    min_schema_version: int,
    done_key: str,
) -> bool:
    from core.schema_core.schema_migrate_version import get_schema_version
    from core.services_core import kv_state
    from core.services_core.db_state import get_readonly_db

    if get_schema_version(get_readonly_db()) < min_schema_version:
        return False
    return kv_state.get(done_key) != "1"


def _should_run_post_v81_vacuum_analyze() -> bool:
    return _should_run_post_migration_vacuum_analyze(
        min_schema_version=81,
        done_key=POST_V81_VACUUM_ANALYZE_DONE_KEY,
    )


def _is_database_locked_error(exc: BaseException) -> bool:
    return "database is locked" in str(exc).lower()


def _get_gateway_health_probe():
    try:
        from core.gateway.backend_registry import get_probe
        return get_probe()
    except Exception:
        return None


def _run_gateway_probe_method(probe, method_name: str, timeout: float = 30.0) -> None:
    import asyncio

    method = getattr(probe, method_name)
    task = getattr(probe, "_task", None)
    loop = task.get_loop() if task is not None else getattr(probe, "_event_loop", None)
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(method(), loop)
        try:
            future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise
        return
    asyncio.run(method())


def _pause_gateway_health_probe(logger) -> tuple[object | None, bool]:
    probe = _get_gateway_health_probe()
    if probe is None:
        return None, False
    is_running = getattr(probe, "is_running", None)
    should_resume = bool(is_running()) if callable(is_running) else getattr(probe, "_task", None) is not None
    if not should_resume:
        return probe, False
    _run_gateway_probe_method(probe, "stop")
    logger.info("post-v81 VACUUM+ANALYZE paused gateway health probe")
    return probe, True


def _resume_gateway_health_probe(probe: object | None, should_resume: bool, logger) -> None:
    if probe is None or not should_resume:
        return
    try:
        _run_gateway_probe_method(probe, "start")
        logger.info("post-v81 VACUUM+ANALYZE resumed gateway health probe")
    except Exception:
        logger.warning("post-v81 VACUUM+ANALYZE failed to resume gateway health probe", exc_info=True)


def _run_post_migration_vacuum_analyze_with_retry(
    logger,
    *,
    label: str,
    max_attempts: int,
    retry_base: float,
) -> None:
    from core.scheduler_core.builtin_jobs_db import db_analyze, db_vacuum

    for attempt in range(1, max_attempts + 1):
        try:
            db_vacuum()
            db_analyze()
            return
        except Exception as exc:
            if (
                not _is_database_locked_error(exc)
                or attempt >= max_attempts
            ):
                raise
            delay = retry_base * (2 ** (attempt - 1))
            logger.warning(
                "%s VACUUM+ANALYZE database locked; retrying in %.1fs "
                "(attempt %d/%d)",
                label,
                delay,
                attempt + 1,
                max_attempts,
            )
            time.sleep(delay)


def _run_post_v81_vacuum_analyze_with_retry(logger) -> None:
    _run_post_migration_vacuum_analyze_with_retry(
        logger,
        label="post-v81",
        max_attempts=POST_V81_VACUUM_ANALYZE_MAX_ATTEMPTS,
        retry_base=POST_V81_VACUUM_ANALYZE_RETRY_BASE_SECONDS,
    )


def run_post_migration_vacuum_analyze_once(
    *,
    min_schema_version: int,
    done_key: str,
    label: str,
    max_attempts: int = POST_MIGRATION_VACUUM_ANALYZE_MAX_ATTEMPTS,
    retry_base: float = POST_MIGRATION_VACUUM_ANALYZE_RETRY_BASE_SECONDS,
    wait_for_idle: bool = True,
) -> bool:
    """Run one post-migration VACUUM+ANALYZE, marking success in kv_state."""
    import logging

    logger = logging.getLogger(__name__)
    probe = None
    resume_probe = False
    try:
        if wait_for_idle:
            _wait_for_startup_idle()
        if not _should_run_post_migration_vacuum_analyze(
            min_schema_version=min_schema_version,
            done_key=done_key,
        ):
            return False

        from core.services_core import kv_state

        logger.info("%s VACUUM+ANALYZE starting", label)
        probe, resume_probe = _pause_gateway_health_probe(logger)
        _run_post_migration_vacuum_analyze_with_retry(
            logger,
            label=label,
            max_attempts=max_attempts,
            retry_base=retry_base,
        )
        kv_state.set(done_key, "1")
        logger.info("%s VACUUM+ANALYZE completed", label)
        return True
    except Exception:
        logger.warning(
            "%s VACUUM+ANALYZE failed; will retry on next boot",
            label,
            exc_info=True,
        )
        return False
    finally:
        _resume_gateway_health_probe(probe, resume_probe, logger)


def run_post_v81_vacuum_analyze_once(*, wait_for_idle: bool = True) -> bool:
    """Run post-v81 VACUUM+ANALYZE once, marking success in kv_state."""
    return run_post_migration_vacuum_analyze_once(
        min_schema_version=81,
        done_key=POST_V81_VACUUM_ANALYZE_DONE_KEY,
        label="post-v81",
        max_attempts=POST_V81_VACUUM_ANALYZE_MAX_ATTEMPTS,
        retry_base=POST_V81_VACUUM_ANALYZE_RETRY_BASE_SECONDS,
        wait_for_idle=wait_for_idle,
    )


def run_post_v82_vacuum_analyze_once(*, wait_for_idle: bool = True) -> bool:
    """Run post-v82 VACUUM+ANALYZE once, marking success in kv_state."""
    return run_post_migration_vacuum_analyze_once(
        min_schema_version=82,
        done_key=POST_V82_VACUUM_ANALYZE_DONE_KEY,
        label="post-v82",
        max_attempts=POST_MIGRATION_VACUUM_ANALYZE_MAX_ATTEMPTS,
        retry_base=POST_MIGRATION_VACUUM_ANALYZE_RETRY_BASE_SECONDS,
        wait_for_idle=wait_for_idle,
    )


def _startup_post_v81_vacuum_analyze() -> None:
    run_post_v81_vacuum_analyze_once()


def _startup_post_v82_vacuum_analyze() -> None:
    run_post_v82_vacuum_analyze_once()


def build_background_tasks() -> list[BackgroundTaskDef]:
    """Return startup background tasks in runtime order."""
    return [
        BackgroundTaskDef("thumb_cleanup", ["full"], _startup_thumb_cleanup),
        BackgroundTaskDef(
            "analyze",
            ["full"],
            _startup_analyze,
            env_enable="TAGDB_ENABLE_ANALYZE",
            env_disable="TAGDB_DISABLE_ANALYZE",
        ),
        BackgroundTaskDef(
            "file_meta_cache",
            ["full"],
            _startup_file_meta_cache,
            env_enable="TAGDB_ENABLE_FILE_CACHE",
            critical=True,
        ),
        BackgroundTaskDef(
            "stats_warmup",
            ["full"],
            _startup_stats_warmup,
            env_enable="TAGDB_ENABLE_STATS_PRELOAD",
            env_disable="TAGDB_DISABLE_STATS_PRELOAD",
        ),
        BackgroundTaskDef(
            "llm_router_refresh",
            ["full", "gateway", "server"],
            _startup_llm_router_refresh,
            env_disable="TAGDB_DISABLE_LLM_ROUTER_REFRESH",
        ),
        BackgroundTaskDef(
            "hailo_auto_reboot_judge",
            ["full"],
            startup_hailo_auto_reboot_judge,
            env_disable="TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE",
        ),
        BackgroundTaskDef(
            "wd_tagger_config_migrate_v2",
            ["full"],
            _startup_wd_tagger_config_migrate_v2,
            env_disable="TAGDB_DISABLE_WD_TAGGER_CONFIG_MIGRATE_V2",
        ),
        BackgroundTaskDef(
            "tag_normalize_backfill",
            ["full"],
            _startup_tag_normalize_backfill,
            env_disable="TAGDB_DISABLE_TAG_NORMALIZE_BACKFILL",
        ),
        BackgroundTaskDef(
            "post_v81_vacuum_analyze",
            ["full"],
            _startup_post_v81_vacuum_analyze,
            env_disable="TAGDB_DISABLE_POST_V81_VACUUM_ANALYZE",
        ),
        BackgroundTaskDef(
            "post_v82_vacuum_analyze",
            ["full"],
            _startup_post_v82_vacuum_analyze,
            env_disable="TAGDB_DISABLE_POST_V82_VACUUM_ANALYZE",
        ),
    ]
