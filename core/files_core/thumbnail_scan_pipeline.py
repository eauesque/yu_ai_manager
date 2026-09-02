"""Pipeline for parallel thumbnail generation during scanning.

Receives IDs of newly added files from the scan loop and pre-generates
thumbnails in a background thread, providing thumbnails simultaneously
with file addition without waiting for the post-scan bulk warmup.

I/O load control:
- Runs at lower priority than the scan itself
- Uses flush intervals to avoid burst I/O
- Groups archive members for single-open processing
"""

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL = 1.0    # Queue drain interval (seconds)
_FLUSH_BATCH_MAX = 50    # Max items per flush
_YIELD_SEC = 0.02        # Yield between batches (20ms)


class ScanThumbnailPipeline:
    """Thumbnail generation worker running alongside scan.

    Usage::

        pipeline = ScanThumbnailPipeline()
        pipeline.start()
        # Inside the scan loop:
        pipeline.enqueue([file_id1, file_id2, ...])
        # On scan completion:
        pipeline.stop()
    """

    def __init__(self) -> None:
        self._queue: deque[int] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._generated = 0

    def start(self) -> None:
        """Start the worker thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._generated = 0
        self._thread = threading.Thread(
            target=self._worker,
            name="thumb-scan-pipe",
            daemon=True,
        )
        self._thread.start()
        logger.info("Scan thumbnail pipeline started")

    def stop(self) -> int:
        """Stop the worker and consume remaining queue items.

        Returns:
            Total number of thumbnails generated
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)
        # Final flush of remaining items
        self._flush_all()
        total = self._generated
        logger.info("Scan thumbnail pipeline stopped: %d thumbnails generated", total)
        return total

    def enqueue(self, file_ids: list[int]) -> None:
        """Add file IDs to the queue (called from scan thread)."""
        if not file_ids:
            return
        with self._lock:
            self._queue.extend(file_ids)

    @property
    def pending(self) -> int:
        """Number of unprocessed items in the queue."""
        with self._lock:
            return len(self._queue)

    def _worker(self) -> None:
        """Main worker loop."""
        _lower_thread_priority()
        while not self._stop_event.is_set():
            self._flush_batch()
            # Wait until next flush (stop_event exits immediately)
            self._stop_event.wait(timeout=_FLUSH_INTERVAL)
        # Remaining items on stop are handled by _flush_all in stop()

    def _drain_ids(self, max_count: int) -> list[int]:
        """Drain up to max_count items from the queue."""
        with self._lock:
            count = min(len(self._queue), max_count)
            if count == 0:
                return []
            ids = [self._queue.popleft() for _ in range(count)]
        return ids

    def _flush_batch(self) -> None:
        """Drain a batch from the queue and generate thumbnails."""
        ids = self._drain_ids(_FLUSH_BATCH_MAX)
        if not ids:
            return
        self._generate_thumbnails(ids)

    def _flush_all(self) -> None:
        """Process all IDs remaining in the queue."""
        while True:
            ids = self._drain_ids(_FLUSH_BATCH_MAX)
            if not ids:
                break
            self._generate_thumbnails(ids)
            time.sleep(_YIELD_SEC)

    def _generate_thumbnails(self, file_ids: list[int]) -> None:
        """Generate thumbnails using warmup_thumbnails_for_ids."""
        try:
            from .thumbnail_batch_warmup import warmup_thumbnails_for_ids
            count = warmup_thumbnails_for_ids(file_ids)
            self._generated += count
            if count > 0:
                logger.debug(
                    "Scan pipeline: generated %d thumbnails (batch=%d)",
                    count, len(file_ids),
                )
        except Exception as exc:
            logger.debug("Scan pipeline batch failed: %s", exc)


def _lower_thread_priority() -> None:
    """Lower the thread priority (best effort)."""
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.GetCurrentThread()
            # THREAD_PRIORITY_LOWEST = -2
            ctypes.windll.kernel32.SetThreadPriority(handle, -2)
        except Exception:
            logger.debug("file metadata step failed", exc_info=True)
    elif sys.platform != "darwin":
        try:
            import os
            os.nice(10)
        except Exception:
            logger.debug("file metadata step failed", exc_info=True)
