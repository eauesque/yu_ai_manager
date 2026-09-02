"""Persistent scan history store.

Subscribes to SCAN_COMPLETE and SCAN_ERROR events and persists
up to MAX_ENTRIES entries as a JSON file in the data directory.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_ENTRIES = 100
_HISTORY_FILE = Path("data") / "scan_history.json"

_lock = threading.Lock()
_entries: list[dict[str, Any]] = []
_initialized = False


def _load() -> None:
    global _entries
    if _HISTORY_FILE.exists():
        try:
            with open(_HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _entries = data[-MAX_ENTRIES:]
        except Exception:
            logger.exception("Failed to load scan history")


def _save() -> None:
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_entries, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save scan history")


def _on_scan_complete(event: Any) -> None:
    d = event.data or {}
    entry: dict[str, Any] = {
        "status": "complete",
        "timestamp": event.timestamp,
        "job_id": d.get("job_id", ""),
        "count": d.get("count", 0),
        "added": d.get("added_count", 0),
        "updated": d.get("updated_count", 0),
        "deleted": d.get("deleted", 0),
        "errors": d.get("errors", 0),
        "elapsed_seconds": d.get("elapsed_seconds", 0),
        "label": d.get("label", ""),
    }
    with _lock:
        _entries.append(entry)
        if len(_entries) > MAX_ENTRIES:
            _entries[:] = _entries[-MAX_ENTRIES:]
        _save()


def _on_scan_start(event: Any) -> None:
    d = event.data or {}
    entry: dict[str, Any] = {
        "status": "started",
        "timestamp": event.timestamp,
        "job_id": d.get("job_id", ""),
        "label": d.get("label", ""),
        "count": 0,
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "errors": 0,
        "elapsed_seconds": 0,
    }
    with _lock:
        _entries.append(entry)
        if len(_entries) > MAX_ENTRIES:
            _entries[:] = _entries[-MAX_ENTRIES:]
        _save()


def _on_scan_error(event: Any) -> None:
    d = event.data or {}
    entry: dict[str, Any] = {
        "status": "error",
        "timestamp": event.timestamp,
        "job_id": d.get("job_id", ""),
        "label": d.get("label", ""),
        "error_message": d.get("message", ""),
        "count": 0,
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "errors": d.get("errors", 1),
        "elapsed_seconds": d.get("elapsed_seconds", 0),
    }
    with _lock:
        _entries.append(entry)
        if len(_entries) > MAX_ENTRIES:
            _entries[:] = _entries[-MAX_ENTRIES:]
        _save()


def get_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent history entries (newest first)."""
    with _lock:
        return list(reversed(_entries[-limit:]))


def init() -> None:
    """Subscribe to scan events and load persisted history."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    _load()

    from core.event_bus import event_bus
    from core.event_bus.event_types import SCAN_COMPLETE, SCAN_ERROR, SCAN_START

    event_bus.subscribe(SCAN_START, _on_scan_start)
    event_bus.subscribe(SCAN_COMPLETE, _on_scan_complete)
    event_bus.subscribe(SCAN_ERROR, _on_scan_error)
    logger.debug("scan_history: subscribed to scan events")
