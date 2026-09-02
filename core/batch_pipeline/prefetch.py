"""Parallel image prefetch pipeline for batch inference.

Shared infrastructure: usable by CLIP indexer, WD tagger, and any
ONNX-based batch processing that needs to overlap I/O with compute.

Architecture:
    ThreadPoolExecutor (N workers) reads & preprocesses images in parallel,
    feeding results into a bounded Queue.  The consumer (main thread) calls
    take_batch() to collect N items and feed them to a batch encoder.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

logger = logging.getLogger(__name__)

_DONE = object()


class ImagePrefetcher:
    """Pre-read and preprocess images in parallel threads.

    Usage::

        items = [(file_id, path), ...]
        with ImagePrefetcher(items, preprocess_fn, workers=6) as pf:
            while True:
                batch = pf.take_batch(32)
                if not batch:
                    break
                ids, arrays = zip(*batch)
                vecs = encoder.encode_batch(np.stack(arrays))

    Args:
        file_items: List of (id, path) tuples to process.
        preprocess_fn: Callable(path) -> np.ndarray (preprocessed image).
        workers: Number of parallel I/O threads.
        queue_depth: Max items buffered ahead of consumer.
    """

    def __init__(
        self,
        file_items: list[tuple[int, str]],
        preprocess_fn: Callable[[str], np.ndarray],
        workers: int = 6,
        queue_depth: int = 128,
    ) -> None:
        self._items = file_items
        self._preprocess_fn = preprocess_fn
        self._workers = workers
        self._queue: queue.Queue = queue.Queue(maxsize=queue_depth)
        self._errors = 0
        self._error_lock = threading.Lock()
        self._failed_ids: list = []
        self._stop = threading.Event()
        self._producer: threading.Thread | None = None
        self._done = False

    def start(self) -> None:
        """Start background prefetch threads."""
        self._producer = threading.Thread(
            target=self._produce, daemon=True, name="img-prefetch",
        )
        self._producer.start()

    def stop(self) -> None:
        """Signal stop and drain the queue."""
        self._stop.set()
        # Drain queue to unblock any put() calls in producer
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    @property
    def errors(self) -> int:
        with self._error_lock:
            return self._errors

    @property
    def failed_ids(self) -> list:
        with self._error_lock:
            return list(self._failed_ids)

    def take_batch(
        self, batch_size: int, timeout: float = 30.0
    ) -> list[tuple[int, np.ndarray]]:
        """Collect up to *batch_size* preprocessed (id, array) pairs.

        Returns empty list when all items have been consumed.
        """
        if self._done:
            return []

        batch: list[tuple[int, np.ndarray]] = []
        deadline = time.monotonic() + timeout

        while len(batch) < batch_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                item = self._queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self._producer and not self._producer.is_alive() and self._queue.empty():
                    self._done = True
                    break
                continue
            if item is _DONE:
                self._done = True
                break
            batch.append(item)
        return batch

    # ── Producer (background thread) ────────────────────────────────

    def _produce(self) -> None:
        """Submit items to thread pool and enqueue results."""
        with ThreadPoolExecutor(
            max_workers=self._workers,
            thread_name_prefix="prefetch",
        ) as pool:
            pending: list[Future] = []
            submit_idx = 0
            # Submission window: keep ~workers*3 futures in flight
            window = self._workers * 3

            while submit_idx < len(self._items) and not self._stop.is_set():
                # Submit up to window size
                while len(pending) < window and submit_idx < len(self._items):
                    if self._stop.is_set():
                        break
                    fid, path = self._items[submit_idx]
                    submit_idx += 1
                    pending.append(pool.submit(self._load_one, fid, path))

                # Harvest completed futures (preserve order)
                still_pending: list[Future] = []
                for fut in pending:
                    if self._stop.is_set():
                        fut.cancel()
                        continue
                    if fut.done():
                        result = fut.result()
                        if result is not None:
                            self._queue.put(result)
                    else:
                        still_pending.append(fut)
                pending = still_pending

                # Brief sleep to avoid busy-wait
                if pending and not self._stop.is_set():
                    time.sleep(0.005)

            # Wait for remaining futures
            for fut in pending:
                if self._stop.is_set():
                    fut.cancel()
                    continue
                try:
                    result = fut.result(timeout=30)
                    if result is not None:
                        self._queue.put(result)
                except Exception:
                    logger.warning("step failed", exc_info=True)

        self._queue.put(_DONE)

    def _load_one(
        self, fid: int, path: str
    ) -> tuple[int, np.ndarray] | None:
        """Load and preprocess one image. Returns None on failure."""
        if self._stop.is_set():
            return None
        try:
            arr = self._preprocess_fn(path)
            # Strip leading batch dim: (1,3,H,W) -> (3,H,W)
            if arr.ndim == 4 and arr.shape[0] == 1:
                arr = arr[0]
            return (fid, arr)
        except Exception:
            with self._error_lock:
                self._errors += 1
                self._failed_ids.append(fid)
            return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
