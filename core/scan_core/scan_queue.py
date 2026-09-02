"""Scan queue -- queues requests when a scan is already running.

Thread-safe FIFO queue + JSON file persistence.
Queue contents are preserved across server restarts.
"""

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Special root value indicating scan-all
SCAN_ALL_ROOT = "__all__"

# Queue file storage location (data/ directory)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QUEUE_FILE = _PROJECT_ROOT / "data" / "scan_queue.json"


@dataclass
class ScanQueueItem:
    """A single entry in the queue."""

    queue_id: str
    root: str
    recursive: bool
    force: bool
    scan_zips: bool
    queued_at: float
    label: str
    source: str  # "manual" | "scan-all" | "api"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScanQueue:
    """Thread-safe scan queue. Persisted via JSON file."""

    MAX_QUEUE_SIZE = 50

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[ScanQueueItem] = []
        self._load()

    # -- Persistence -----------------------------------------------------------

    def _load(self) -> None:
        if not _QUEUE_FILE.exists():
            return
        try:
            data = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            self._items = [ScanQueueItem(**item) for item in data]
            logger.info("scan_queue: %d items restored", len(self._items))
        except Exception as e:
            logger.warning("scan_queue load failed: %s", e)
            self._items = []

    def _save(self) -> None:
        _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
            [item.to_dict() for item in self._items],
            ensure_ascii=False, indent=2,
        )
        fd, tmp = tempfile.mkstemp(dir=str(_QUEUE_FILE.parent), suffix=".tmp")
        try:
            os.write(fd, data.encode("utf-8"))
            os.close(fd)
            fd = -1
            os.replace(tmp, str(_QUEUE_FILE))
        except Exception:
            if fd != -1:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    # -- Queue operations -------------------------------------------------------

    def enqueue(
        self,
        root: str,
        recursive: bool = True,
        force: bool = False,
        scan_zips: bool = True,
        label: str = "",
        source: str = "manual",
    ) -> ScanQueueItem:
        """Add to queue. Raises ValueError if an identical root is already queued."""
        with self._lock:
            for item in self._items:
                if item.root == root:
                    raise ValueError(f"'{root}' is already in queue")
            if len(self._items) >= self.MAX_QUEUE_SIZE:
                raise ValueError("Queue is full")

            item = ScanQueueItem(
                queue_id=uuid.uuid4().hex[:12],
                root=root,
                recursive=recursive,
                force=force,
                scan_zips=scan_zips,
                queued_at=time.time(),
                label=label or root,
                source=source,
            )
            self._items.append(item)
            self._save()
            return item

    def pop_next(self) -> ScanQueueItem | None:
        """Dequeue and return the first item. None if empty."""
        with self._lock:
            if not self._items:
                return None
            item = self._items.pop(0)
            self._save()
            return item

    def remove(self, queue_id: str) -> bool:
        """Delete individual item by queue_id."""
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i.queue_id != queue_id]
            if len(self._items) < before:
                self._save()
                return True
            return False

    def clear(self) -> int:
        """Clear all. Number of items deletedreturn."""
        with self._lock:
            count = len(self._items)
            if count > 0:
                self._items.clear()
                self._save()
            return count

    def list_items(self) -> list[dict[str, Any]]:
        with self._lock:
            return [item.to_dict() for item in self._items]

    def size(self) -> int:
        with self._lock:
            return len(self._items)


# -- Singleton --
scan_queue = ScanQueue()
