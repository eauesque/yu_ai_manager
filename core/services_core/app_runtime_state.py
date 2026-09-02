"""Application runtime state shared across DB/service helpers."""

from __future__ import annotations

import time
from contextlib import suppress
from pathlib import Path

DB_PATH: Path | None = None
CONFIG: dict | None = None
_START_TIME: float | None = None
_BOOT_READY: bool = False
_STARTUP_MIGRATION_INFO: dict | None = None
_STARTUP_STATUS: dict | None = None


def init_app_state(db_path: Path, config: dict) -> None:
    """Initialize application runtime state at startup."""
    global DB_PATH, CONFIG, _START_TIME
    DB_PATH = db_path.resolve()
    CONFIG = config
    _START_TIME = time.time()
    with suppress(Exception):
        from core.search_api.search_page_cache import search_page_cache

        search_page_cache.invalidate()


def get_db_path() -> Path:
    """Return the current DB path."""
    if DB_PATH is None:
        raise RuntimeError("DB_PATH is not initialized")
    return DB_PATH


def get_vectors_db_path() -> Path:
    """Return vectors.db path (sibling to tags.db in same directory)."""
    return get_db_path().parent / "vectors.db"


def get_config() -> dict:
    """Return the current application config."""
    return CONFIG or {}


def get_start_time() -> float:
    """Return the application start time."""
    return _START_TIME or time.time()


def set_boot_ready() -> None:
    """Mark server initialization as complete."""
    global _BOOT_READY
    _BOOT_READY = True


def is_boot_ready() -> bool:
    """Check whether the server has finished initialization."""
    return _BOOT_READY


def set_startup_migration_info(info: dict | None) -> None:
    """Persist startup-only schema migration info for the current process."""
    global _STARTUP_MIGRATION_INFO
    _STARTUP_MIGRATION_INFO = info


def get_startup_migration_info() -> dict | None:
    """Return startup-only schema migration info for the current process."""
    return _STARTUP_MIGRATION_INFO


def set_startup_status(info: dict | None) -> None:
    """Persist startup status info for boot-time UI notices."""
    global _STARTUP_STATUS
    _STARTUP_STATUS = info


def get_startup_status() -> dict | None:
    """Return startup status info for boot-time UI notices."""
    return _STARTUP_STATUS
