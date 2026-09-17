"""Core watcher logic: observe scan_roots and sync changes to DB.

Archive scanning logic is in watcher_archive.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

try:
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore[assignment,misc]

# Re-export for backward compatibility
from watcher_archive import flush_archives, mark_archive_entries_deleted  # noqa: F401
from watcher_handler import ScanFileHandler

logger = logging.getLogger(__name__)

_ARCHIVE_EXTS = {".zip", ".7z"}
# Limit files processed per flush cycle so one large batch can't hold the
# DB writer thread for minutes. Overflow is re-queued for the next cycle.
_FLUSH_BATCH_MAX = 200


class ScanWatcher:
    """Watch scan_roots for file changes and sync to DB incrementally."""

    def __init__(self, debounce_seconds: float = 3.0):
        self._observer: Observer | None = None  # type: ignore[assignment]
        self._debounce = debounce_seconds
        self._pending: dict[str, tuple] = {}  # path -> (action, timestamp)
        self._lock = threading.Lock()
        self._flush_timer: threading.Timer | None = None
        self._watched_roots: list[str] = []
        self._watched_roots_resolved: list[str] = []  # junction-resolved cache
        self._running = False
        self.stats = {"added": 0, "modified": 0, "deleted": 0, "errors": 0}

    @property
    def running(self) -> bool:
        return self._running

    @property
    def watched_roots(self) -> list[str]:
        return list(self._watched_roots)

    def _resolve_path(self, filepath: str) -> str:
        """Resolve junctions/aliases (e.g. C:\\Users mapped from localized names)."""
        is_unc = filepath.startswith("\\\\") or filepath.startswith("//")
        if is_unc:
            return os.path.normcase(os.path.normpath(filepath))
        try:
            resolved = str(Path(filepath).resolve())
            return os.path.normcase(os.path.normpath(resolved))
        except (OSError, ValueError):
            return os.path.normcase(os.path.normpath(filepath))

    def _is_under_watched_root(self, filepath: str) -> bool:
        """Check if a file path falls under one of the watched roots.

        Uses resolved paths to handle Windows junction aliases like
        C:\\Users on Japanese Windows.
        """
        norm = self._resolve_path(filepath)
        for root_resolved in self._watched_roots_resolved:
            if norm.startswith(root_resolved + os.sep) or norm == root_resolved:
                return True
        return False

    def start(self, roots: list[dict[str, Any]], scan_exts: set, db_path: Path, config: dict) -> None:
        """Start watching the given scan_roots."""
        if Observer is None:
            raise RuntimeError("watchdog is not installed")
        if self._running:
            logger.warning("Watcher already running, ignoring start()")
            return

        self._db_path = db_path
        self._config = config
        self._scan_exts = scan_exts

        handler = ScanFileHandler(self._on_fs_event, scan_exts)
        self._observer = Observer()
        self._watched_roots = []

        for root_entry in roots:
            root_path = root_entry.get("path", "") if isinstance(root_entry, dict) else str(root_entry)
            if not root_path:
                continue
            p = Path(root_path)
            try:
                is_dir = p.is_dir()
            except OSError as exc:
                logger.warning("Watcher: skipping inaccessible root: %s (%s)", root_path, exc)
                continue
            if not is_dir:
                logger.warning("Watcher: skipping non-existent root: %s", root_path)
                continue
            recursive = root_entry.get("recursive", True) if isinstance(root_entry, dict) else True
            self._observer.schedule(handler, str(p), recursive=recursive)
            self._watched_roots.append(root_path)
            logger.info("Watcher: watching %s (recursive=%s)", root_path, recursive)

        # Pre-resolve junction aliases for efficient comparison
        self._watched_roots_resolved = [
            self._resolve_path(r) for r in self._watched_roots
        ]
        logger.info("Watcher: resolved roots: %s", self._watched_roots_resolved)

        if not self._watched_roots:
            logger.warning("Watcher: no valid roots to watch")
            return

        self._observer.daemon = True
        self._observer.start()
        self._running = True

        from core.event_bus import emit
        from core.event_bus.event_types import WATCHER_STARTED
        emit(WATCHER_STARTED, {"roots": self._watched_roots}, source="auto-scan-watcher")
        logger.info("Watcher started: %d roots", len(self._watched_roots))

    def restart(self, roots: list[dict[str, Any]], scan_exts: set,
                db_path: Path, config: dict) -> None:
        """Stop and restart with updated roots."""
        if self._running:
            self.stop()
        self.start(roots, scan_exts, db_path, config)

    def stop(self) -> None:
        """Stop the watcher."""
        if not self._running:
            return
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None
        # Flush remaining events before stopping
        self._flush_pending()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._running = False
        self._watched_roots = []
        self._watched_roots_resolved = []

        from core.event_bus import emit
        from core.event_bus.event_types import WATCHER_STOPPED
        emit(WATCHER_STOPPED, {"stats": dict(self.stats)}, source="auto-scan-watcher")
        logger.info("Watcher stopped")

    def _on_fs_event(self, path: str, action: str) -> None:
        """Receive event from handler, buffer with debounce."""
        with self._lock:
            self._pending[path] = (action, time.time())
            # Reset debounce timer
            if self._flush_timer:
                self._flush_timer.cancel()
            self._flush_timer = threading.Timer(self._debounce, self._flush_pending)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def _flush_pending(self) -> None:
        """Process all buffered events in a single batch."""
        with self._lock:
            batch = dict(self._pending)
            self._pending.clear()
            self._flush_timer = None
            # Snapshot lifecycle variables under lock to prevent TOCTOU
            # between lifecycle changes (start/stop/restart) and flush.
            roots_snapshot = list(self._watched_roots)
            is_under_root_snapshot = self._is_under_watched_root
            config_snapshot = dict(self._config) if self._config else {}

        if not batch:
            return

        # Skip if a scan job is currently running
        try:
            from core.jobs_core.jobs import job_manager
            if job_manager.is_running("scan") or job_manager.is_running("scan-all"):
                logger.debug("Watcher: scan job running, deferring %d events", len(batch))
                # Re-queue the events
                with self._lock:
                    for path, val in batch.items():
                        if path not in self._pending:
                            self._pending[path] = val
                    if self._pending and not self._flush_timer:
                        self._flush_timer = threading.Timer(self._debounce * 2, self._flush_pending)
                        self._flush_timer.daemon = True
                        self._flush_timer.start()
                return
        except Exception:
            logger.debug("job_manager unavailable; proceeding", exc_info=True)

        # Cap batch size to prevent the DB writer from blocking for minutes
        # when many files arrive at once. Overflow is re-queued immediately.
        overflow: dict[str, tuple] = {}
        if len(batch) > _FLUSH_BATCH_MAX:
            items = list(batch.items())
            batch = dict(items[:_FLUSH_BATCH_MAX])
            overflow = dict(items[_FLUSH_BATCH_MAX:])

        added = modified = deleted = errors = 0

        try:
            from core.services_core.auto_scan_watcher_service import (
                process_watcher_batch,
            )
            from core.services_core.db_write import submit_db_write

            def _write_batch():
                return process_watcher_batch(
                    batch,
                    config_snapshot,
                    roots_snapshot,
                    is_under_root_snapshot,
                )

            added, modified, deleted, errors = submit_db_write(_write_batch)
        except Exception:
            logger.error("Watcher: flush failed", exc_info=True)
            errors += len(batch)

        self.stats["added"] += added
        self.stats["modified"] += modified
        self.stats["deleted"] += deleted
        self.stats["errors"] += errors

        from core.event_bus import emit
        from core.event_bus.event_types import WATCHER_SYNC
        emit(WATCHER_SYNC, {
            "batch_added": added,
            "batch_modified": modified,
            "batch_deleted": deleted,
            "batch_errors": errors,
            "total": dict(self.stats),
        }, source="auto-scan-watcher")
        logger.info("Watcher sync: +%d ~%d -%d err=%d", added, modified, deleted, errors)

        if overflow:
            with self._lock:
                for path, val in overflow.items():
                    if path not in self._pending:
                        self._pending[path] = val
                if self._pending and not self._flush_timer:
                    self._flush_timer = threading.Timer(self._debounce * 0.5, self._flush_pending)
                    self._flush_timer.daemon = True
                    self._flush_timer.start()
