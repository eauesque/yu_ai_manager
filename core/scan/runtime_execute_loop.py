"""Execution loop for background scan runtime — main loop."""

import contextlib
import logging
import time
from collections import deque

from core.models_core.models_tags import reset_tag_cache
from core.scan.common import needs_backfill
from core.scan.runtime_execute_helpers import (
    ARCHIVE_COMMIT_INTERVAL,
    COMMIT_INTERVAL,
    _lower_io_priority,
)
from core.scan.runtime_execute_items import (
    is_archive_path,
    process_archive_batch,
    process_regular_file,
)
from core.scan.runtime_execute_monitor import ScanLoopMonitor
from core.scan_core.scan_state import save_scan_state

logger = logging.getLogger(__name__)


def execute_scan_loop(
    con,
    all_files,
    config,
    *,
    root_path: str,
    recursive: bool,
    force: bool,
    scan_zips: bool,
    compute_hash_explicit: bool,
    job,
    archive_cache=None,
):
    _lower_io_priority()
    reset_tag_cache()

    # Thumbnail scan pipeline: generate thumbnails in parallel with new file additions
    thumb_pipeline = None
    if config.get("thumbnail_prewarm", True):
        try:
            from core.files_core.thumbnail_scan_pipeline import ScanThumbnailPipeline
            thumb_pipeline = ScanThumbnailPipeline()
            thumb_pipeline.start()
        except Exception as exc:
            logger.debug("Thumbnail scan pipeline unavailable: %s", exc)

    # Convert to deque for popleft consumption — immediately free memory of processed paths
    file_queue = deque(all_files)
    total_files = len(file_queue)
    del all_files  # Release reference to original list
    started_at = time.time()

    # Check once whether any files need hash backfill.
    # If all hashes are populated, skip per-file backfill checks entirely.
    backfill_pending = needs_backfill(con)
    skip_backfill = backfill_pending == 0
    if backfill_pending > 0:
        logger.info("hash backfill: %d files with NULL hash detected", backfill_pending)

    save_scan_state(
        root_path,
        recursive,
        force,
        scan_zips,
        current=0,
        total=total_files,
        started_at=started_at,
    )

    scan_throttle_s = config.get("scan_throttle_ms", 10) / 1000.0
    archive_throttle_s = config.get("archive_throttle_ms", 20) / 1000.0

    count = 0
    errors = 0
    backfilled = 0
    added_ids: list = []
    updated_ids: list = []
    monitor = ScanLoopMonitor(
        con,
        job,
        root_path=root_path,
        recursive=recursive,
        force=force,
        scan_zips=scan_zips,
        total_files=total_files,
        started_at=started_at,
        commit_min_changes=int(config.get("scan_commit_min_changes", 3)),
        commit_max_defer_sec=float(config.get("scan_commit_max_defer_sec", 5.0)),
    )

    while file_queue:
        if monitor.check_cancelled(count):
            if thumb_pipeline:
                with contextlib.suppress(Exception):
                    thumb_pipeline.stop()
            return {
                "cancelled": True, "count": count, "errors": errors,
                "total_files": total_files, "added_ids": added_ids,
                "updated_ids": updated_ids,
            }

        p = file_queue[0]

        # --- Archive batch path ---
        if is_archive_path(p):
            result = process_archive_batch(
                file_queue,
                con,
                config,
                force=force,
                compute_hash_explicit=compute_hash_explicit,
                skip_backfill=skip_backfill,
                archive_cache=archive_cache,
                thumb_pipeline=thumb_pipeline,
                added_ids=added_ids,
                updated_ids=updated_ids,
            )
            errors += result["errors"]
            backfilled += result["backfilled"]
            count += result["count_delta"]
            if result["error_message"] and errors <= 5:
                job.update(message=f"Error: {result['detail']}: {result['error_message']}")
            job.progress(count, total_files, result["detail"])
            monitor.emit_progress(count, result["detail"])

            # Throttle once after archive batch
            if archive_throttle_s > 0:
                time.sleep(archive_throttle_s)

            monitor.commit_if_due(count, ARCHIVE_COMMIT_INTERVAL)
            monitor.run_periodic_maintenance(count, backfilled)
            continue

        # --- Regular file path ---
        file_queue.popleft()
        result = process_regular_file(
            p,
            con,
            config,
            force=force,
            compute_hash_explicit=compute_hash_explicit,
            skip_backfill=skip_backfill,
            thumb_pipeline=thumb_pipeline,
            added_ids=added_ids,
            updated_ids=updated_ids,
        )
        errors += result["errors"]
        backfilled += result["backfilled"]
        count += result["count_delta"]
        if result["error_message"] and errors <= 5:
            job.update(message=f"Error: {result['detail']}: {result['error_message']}")
        job.progress(count, total_files, result["detail"])

        if scan_throttle_s > 0:
            time.sleep(scan_throttle_s)

        monitor.emit_progress(count, result["detail"])
        monitor.commit_if_due(count, COMMIT_INTERVAL)
        monitor.run_periodic_maintenance(count, backfilled)

    if backfilled > 0:
        logger.info(f"hash backfill complete: {backfilled} hashes computed")
    monitor.commit_now(count)

    # Stop thumbnail pipeline (drain remaining queue)
    thumb_generated = 0
    if thumb_pipeline:
        try:
            thumb_generated = thumb_pipeline.stop()
        except Exception as exc:
            logger.debug("Thumbnail pipeline stop error: %s", exc)

    return {
        "cancelled": False,
        "count": count,
        "errors": errors,
        "total_files": total_files,
        "added_ids": added_ids,
        "updated_ids": updated_ids,
        "backfilled": backfilled,
        "thumb_generated": thumb_generated,
    }
