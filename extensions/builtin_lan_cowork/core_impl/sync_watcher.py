"""extensions/builtin_lan_cowork/core_impl/sync_watcher.py
Watch wildcard directories for changes and notify SyncManager.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from .sync_manager import SyncManager

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 2.0


class _SyncEventHandler(FileSystemEventHandler):
    """Debounced file change handler."""

    def __init__(self, root: Path, sync_mgr: SyncManager) -> None:
        self._root = root.resolve()
        self._sync = sync_mgr
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = Path(event.src_path)
        try:
            rel = src.relative_to(self._root).as_posix()
        except ValueError:
            return
        if rel.endswith(".bak"):
            return
        with self._lock:
            self._pending[rel] = time.time()
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = list(self._pending.keys())
            self._pending.clear()
        for rel_path in paths:
            self._sync.notify_local_change(rel_path)


class SyncWatcher:
    """Watches a WC directory and notifies SyncManager on changes."""

    def __init__(self, root: Path, sync_mgr: SyncManager) -> None:
        self._root = root.resolve()
        self._sync = sync_mgr
        self._observer: Observer | None = None

    def start(self) -> None:
        if self._observer:
            return
        handler = _SyncEventHandler(self._root, self._sync)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._root), recursive=True)
        self._observer.start()
        logger.info("SyncWatcher started: %s", self._root)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("SyncWatcher stopped")
