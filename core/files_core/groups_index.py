"""Server-side folder/archive group index with disk cache.

Computes group membership for all non-deleted files and caches the result
as ``cache/groups_index.json``.  The cache is keyed on
``(file_count, max_mtime)`` so any file addition, deletion, or modification
automatically invalidates it.
"""

import contextlib
import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

from core.files_core.groups_index_builder import (
    build_groups_index as _build_groups_index,
)
from core.files_core.groups_index_builder import (
    db_signature as _db_signature,
)

_CACHE_VERSION = 4  # v4: Unified ZIP/7z/RAR into combined archive groups


def _cache_path() -> Path:
    from core.paths import cache_path
    return cache_path("groups_index.json")

# In-memory cache — skip JSON parse if disk mtime hasn't changed
_groups_cond = threading.Condition()
_groups_building = False
_groups_cache: dict | None = None
_groups_cache_mtime: float = 0


# ── helpers ──────────────────────────────────────────────────────────

def build_groups_index(db) -> dict:
    return _build_groups_index(db, _CACHE_VERSION)


# ── cache management ─────────────────────────────────────────────────

def get_groups_index_with_meta(db) -> tuple[dict, str]:
    """Return cached groups index, rebuilding if stale.

    Two-tier cache: in-memory + disk:
    1. If cache path mtime is unchanged, return from memory (stat only)
    2. If disk cache is valid, parse JSON and return
    3. If neither is valid, rebuild from DB
    """
    global _groups_building, _groups_cache, _groups_cache_mtime

    cache_path = _cache_path()
    while True:
        # 1) In-memory cache: fast path with mtime comparison only
        try:
            current_mtime = cache_path.stat().st_mtime if cache_path.exists() else 0
        except OSError:
            current_mtime = 0
        with _groups_cond:
            if _groups_cache is not None and current_mtime == _groups_cache_mtime:
                return _groups_cache, "memory"

        file_count, max_mtime = _db_signature(db)

        # 2) Load disk cache without holding the global condition.
        disk_cached = None
        disk_mtime = current_mtime
        if current_mtime:
            try:
                disk_cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                disk_cached = None
        if (disk_cached is not None
                and disk_cached.get("file_count") == file_count
                and disk_cached.get("max_mtime") == max_mtime
                and disk_cached.get("cache_version") == _CACHE_VERSION):
            with _groups_cond:
                _groups_cache = disk_cached
                _groups_cache_mtime = disk_mtime
            return disk_cached, "disk"

        # 3) Single-flight rebuild. Waiters release the condition while the
        # active builder scans the DB and writes the cache file.
        with _groups_cond:
            try:
                latest_mtime = cache_path.stat().st_mtime if cache_path.exists() else 0
            except OSError:
                latest_mtime = 0
            if _groups_cache is not None and latest_mtime == _groups_cache_mtime:
                return _groups_cache, "memory"
            if _groups_building:
                _groups_cond.wait()
                continue
            _groups_building = True

        try:
            index = build_groups_index(db)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
            try:
                built_mtime = cache_path.stat().st_mtime
            except OSError:
                built_mtime = 0
        except Exception:
            with _groups_cond:
                _groups_building = False
                _groups_cond.notify_all()
            raise

        with _groups_cond:
            _groups_cache = index
            _groups_cache_mtime = built_mtime
            _groups_building = False
            _groups_cond.notify_all()
            return index, "rebuild"


def get_groups_index(db) -> dict:
    index, _source = get_groups_index_with_meta(db)
    return index


_bg_rebuild_lock = threading.Lock()
_bg_rebuild_active = False


def try_get_groups_index_fast(db) -> tuple[dict, str] | None:
    """Return (index, source) only if available without a full rebuild scan.

    Used by ``/api/search-grouped/warm`` to avoid blocking the DB executor
    for 5-10 seconds when the disk cache signature is stale. Returns
    ``None`` if a rebuild would be required.
    """
    global _groups_cache, _groups_cache_mtime
    cache_path = _cache_path()
    try:
        current_mtime = cache_path.stat().st_mtime if cache_path.exists() else 0
    except OSError:
        current_mtime = 0
    with _groups_cond:
        if _groups_cache is not None and current_mtime == _groups_cache_mtime:
            return _groups_cache, "memory"

    # Disk-cache fast path requires a signature match without a rebuild.
    if not current_mtime:
        return None
    file_count, max_mtime = _db_signature(db)
    try:
        disk_cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if (
        disk_cached.get("file_count") == file_count
        and disk_cached.get("max_mtime") == max_mtime
        and disk_cached.get("cache_version") == _CACHE_VERSION
    ):
        with _groups_cond:
            _groups_cache = disk_cached
            _groups_cache_mtime = current_mtime
        return disk_cached, "disk"
    return None


def schedule_background_rebuild() -> bool:
    """Spawn a daemon thread that rebuilds the groups index, deduped.

    Returns ``True`` if a fresh background rebuild was scheduled,
    ``False`` if one is already running (single-flight).
    """
    global _bg_rebuild_active
    with _bg_rebuild_lock:
        if _bg_rebuild_active:
            return False
        _bg_rebuild_active = True

    def _runner() -> None:
        global _bg_rebuild_active
        try:
            from core.services_core.db_api import get_readonly_db
            con = get_readonly_db()
            get_groups_index_with_meta(con)
        except Exception:
            logger.debug("file metadata step failed", exc_info=True)
        finally:
            with _bg_rebuild_lock:
                _bg_rebuild_active = False

    threading.Thread(
        target=_runner,
        name="groups-index-rebuild",
        daemon=True,
    ).start()
    return True


def invalidate_cache() -> None:
    """Delete the disk cache so the next ``get_groups_index`` rebuilds."""
    global _groups_cache, _groups_cache_mtime
    with _groups_cond:
        _groups_cache = None
        _groups_cache_mtime = 0
        with contextlib.suppress(OSError):
            _cache_path().unlink(missing_ok=True)


def get_all_rep_ids(index: dict) -> list[tuple[int, str]]:
    """Extract all representative (id, key) pairs from a groups index.

    Used by ``/api/container-thumb-ids`` to determine which thumbnails
    need generating.
    """
    result = []
    seen: set[int] = set()
    for groups in (index.get("folders", {}), index.get("zips", {})):
        for _key, entry in groups.items():
            for fid in entry.get("reps", []):
                if fid not in seen:
                    seen.add(fid)
                    result.append(fid)
    return result
