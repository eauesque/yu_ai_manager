"""Prewarm thumbnail cache after scan.complete.

Prevents massive cache misses in the grid view right after scan
by pre-generating thumbnails for newly added files in a background thread.

I/O contention mitigation:
- Starts after a cooldown period following scan completion
- Limits workers to 2 (to avoid saturating low-bandwidth storage like RPi)
- Inserts short waits between batches to maintain browser responsiveness
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.event_bus import event_bus
from core.event_bus.event_types import SCAN_COMPLETE

logger = logging.getLogger(__name__)

_MAX_PREWARM = 2000
_POOL_WORKERS = 2
_COOLDOWN_SEC = 3.0       # Wait time after scan completion
_BATCH_YIELD_SEC = 0.05   # Yield between batches (50ms)
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _sort_by_archive_group(file_ids: list) -> list:
    """Group by ZIP/7z archive and return sorted.

    Files within the same archive are contiguous, improving OS file cache hit rate.
    """
    from core.services_core.db_api import get_readonly_db

    if not file_ids:
        return file_ids

    ids = list(dict.fromkeys(file_ids[:_MAX_PREWARM]))
    con = get_readonly_db()
    path_by_id: dict[int, str] = {}
    for chunk in _chunks(ids):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders})", chunk
        )
        path_by_id.update({int(row["id"]): row["path"] for row in cursor})
    rows = [
        {"id": file_id, "path": path}
        for file_id in ids
        if (path := path_by_id.get(file_id))
    ]

    def _archive_key(row):
        path = row["path"]
        # Archive internal paths are delimited by '!' (e.g. /path/to/archive.zip!inner/file.png)
        sep = path.find("!")
        return path[:sep] if sep >= 0 else ""

    rows.sort(key=_archive_key)
    return [r["id"] for r in rows]


def _is_scan_running() -> bool:
    """Check whether a scan is currently running."""
    from core.services_core.db_scan_progress import scan_lock, scan_state

    with scan_lock:
        return scan_state.get("running", False)


def _prewarm_thumbnails(file_ids: list) -> None:
    """Generate thumbnails in parallel in the background.

    Includes a cooldown to avoid I/O load right after scan,
    and aborts if a scan restarts during processing.
    """
    from core.files_core.thumbnail import serve_thumbnail

    # Wait for disk I/O to settle after scan completion
    time.sleep(_COOLDOWN_SEC)

    # Abort if scan restarted during cooldown
    if _is_scan_running():
        logger.info("Thumbnail prewarm skipped: scan restarted during cooldown")
        return

    sorted_ids = _sort_by_archive_group(file_ids)
    count = 0

    with ThreadPoolExecutor(max_workers=_POOL_WORKERS,
                            thread_name_prefix="thumb-pw") as pool:
        # Submit in batches with yields instead of all at once
        batch_size = _POOL_WORKERS * 2
        for start in range(0, len(sorted_ids), batch_size):
            # Check if scan restarted
            if _is_scan_running():
                logger.info(
                    "Thumbnail prewarm paused: scan running (%d/%d done)",
                    count, len(sorted_ids),
                )
                break

            batch = sorted_ids[start:start + batch_size]
            futures = {
                pool.submit(serve_thumbnail, fid): fid
                for fid in batch
            }
            for future in as_completed(futures):
                fid = futures[future]
                try:
                    future.result()
                    count += 1
                except Exception:
                    logger.debug("Prewarm failed for file_id=%s", fid,
                                 exc_info=True)

            # Short yield to maintain responsiveness to browser requests
            time.sleep(_BATCH_YIELD_SEC)

    logger.info("Thumbnail prewarm complete: %d/%d files",
                count, len(sorted_ids))


def on_scan_complete(event) -> None:
    """Handler for the scan.complete event."""
    from core.files_core.thumbnail_common import invalidate_thumbnail_source_cache
    invalidate_thumbnail_source_cache()

    from core.services_core.db_api import get_config

    cfg = get_config()
    if not cfg.get("thumbnail_prewarm", True):
        return

    added_ids = event.data.get("added_ids", [])
    if not added_ids:
        return

    t = threading.Thread(
        target=_prewarm_thumbnails,
        args=(added_ids,),
        name="thumbnail-prewarm",
        daemon=True,
    )
    t.start()


def subscribe_thumbnail_prewarm_events() -> None:
    """Register event handlers for thumbnail prewarming."""
    event_bus.subscribe(SCAN_COMPLETE, on_scan_complete)
    logger.info("Thumbnail prewarm event handlers registered")
