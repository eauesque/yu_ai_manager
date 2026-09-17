"""watchdog FileSystemEventHandler for scan-relevant file events."""

from __future__ import annotations

import os
from collections.abc import Callable

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
except ImportError as exc:
    raise ImportError("watchdog is required: pip install watchdog>=4.0.0") from exc


class ScanFileHandler(FileSystemEventHandler):
    """Filter filesystem events to scan-relevant extensions and forward them."""

    def __init__(self, callback: Callable[[str, str], None], scan_exts: set[str]):
        super().__init__()
        self._callback = callback
        self._scan_exts = scan_exts

    def _is_relevant(self, path: str) -> bool:
        _, ext = os.path.splitext(path)
        return ext.lower() in self._scan_exts

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._is_relevant(event.src_path):
            self._callback(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._is_relevant(event.src_path):
            self._callback(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._is_relevant(event.src_path):
            self._callback(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._is_relevant(event.src_path):
            self._callback(event.src_path, "deleted")
        dest = getattr(event, "dest_path", None)
        if dest and self._is_relevant(dest):
            self._callback(dest, "created")
