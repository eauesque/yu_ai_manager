"""Thumbnail cache cleanup service.

Supports both flat (legacy) and 2-level sharded (v2) cache layouts.
Walks directories recursively so both layouts are handled uniformly.
"""

import contextlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Valid thumbnail extensions
_THUMB_EXTS = frozenset({".jpg", ".webp"})


def _iter_cache_files(cache: Path):
    """Yield all thumbnail files in both flat and sharded layouts."""
    for item in cache.rglob("*"):
        if item.is_file() and item.suffix in _THUMB_EXTS:
            yield item


def cleanup_thumbnail_cache(cache_dir: str | None = None, max_size_mb: int = 500, max_age_days: int = 30):
    import time

    from core.services_core.cache_index import (
        delete_cache_entries,
        iter_thumbnail_entry_records,
        list_thumbnail_entries,
        remove_missing_thumbnail_entries,
        touch_thumbnail_cache_entries_batch,
    )
    from core.services_core.db_api import get_db, get_readonly_db

    if cache_dir is None:
        from core.paths import cache_path
        cache_dir = str(cache_path("thumbnails"))

    cache = Path(cache_dir)
    if not cache.exists():
        return 0

    now = time.time()
    cutoff = now - (max_age_days * 86400)

    files = []
    expired_count = 0
    evicted_count = 0
    removed_keys = []
    existing_keys = set()
    missing_index_rows: list[tuple[Path, int | None]] = []

    con = None
    try:
        con = get_readonly_db()
    except Exception:
        try:
            con = get_db()
        except Exception:
            con = None

    used_entry_records = False
    if con is not None:
        try:
            for entry in iter_thumbnail_entry_records(con):
                used_entry_records = True
                key = str(entry["cache_key"])
                f = Path(str(entry["path"]))
                if not f.is_file():
                    removed_keys.append(key)
                    continue
                existing_keys.add(key)
                access_ts = int(entry["last_access_at"] or 0)
                size_bytes = int(entry["size_bytes"] or 0)
                if size_bytes <= 0:
                    try:
                        size_bytes = f.stat().st_size
                    except OSError:
                        removed_keys.append(key)
                        continue
                if access_ts < cutoff:
                    try:
                        f.unlink()
                        expired_count += 1
                        removed_keys.append(key)
                    except OSError:
                        pass
                else:
                    files.append((access_ts, size_bytes, key, f))
        except Exception as exc:
            logger.debug("Failed to read cache index records: %s", exc)
            used_entry_records = False

    if not used_entry_records:
        index_by_key = {}
        if con is not None:
            try:
                index_by_key = list_thumbnail_entries(con)
            except Exception as exc:
                logger.debug("Failed to read cache index summary: %s", exc)
                index_by_key = {}
        for f in _iter_cache_files(cache):
            key = f.name
            existing_keys.add(key)
            try:
                stat = f.stat()
            except OSError:
                continue
            idx = index_by_key.get(key, {})
            access_ts = int(idx.get("last_access_at") or stat.st_mtime)
            size_bytes = int(idx.get("size_bytes") or stat.st_size)
            if access_ts < cutoff:
                try:
                    f.unlink()
                    expired_count += 1
                    removed_keys.append(key)
                except OSError:
                    pass
            else:
                files.append((access_ts, size_bytes, key, f))
                if con is not None and key not in index_by_key:
                    missing_index_rows.append((f, None))

    if not used_entry_records and missing_index_rows:
        try:
            wcon = get_db()
            touch_thumbnail_cache_entries_batch(wcon, missing_index_rows)
            wcon.commit()
        except Exception as exc:
            logger.debug("Failed to backfill cache index rows: %s", exc)

    if not used_entry_records and con is not None:
        try:
            wcon = get_db()
            remove_missing_thumbnail_entries(wcon, existing_keys)
            wcon.commit()
        except Exception as exc:
            logger.debug("Failed to remove missing cache entries: %s", exc)

    total_size = sum(s for _, s, _, _ in files)
    max_bytes = max_size_mb * 1024 * 1024

    if total_size > max_bytes:
        files.sort(key=lambda x: x[0])
        for _last_access, size, key, f in files:
            if total_size <= max_bytes:
                break
            try:
                f.unlink()
                total_size -= size
                evicted_count += 1
                removed_keys.append(key)
            except OSError:
                pass

    if removed_keys:
        try:
            wcon = get_db()
            delete_cache_entries(wcon, removed_keys)
            wcon.commit()
        except Exception as exc:
            logger.debug("Failed to commit cache cleanup: %s", exc)

    # Prune empty shard directories after eviction
    _prune_empty_shard_dirs(cache)

    removed = expired_count + evicted_count
    if removed > 0:
        remaining_mb = total_size / (1024 * 1024)
        logger.info(
            "Cache cleanup: removed %d thumbnails "
            "(expired=%d, evicted=%d), %.1f MB remaining",
            removed, expired_count, evicted_count, remaining_mb,
        )
    return removed


def _prune_empty_shard_dirs(cache: Path) -> None:
    """Remove empty shard subdirectories (2-level deep)."""
    try:
        for level1 in cache.iterdir():
            if not level1.is_dir() or len(level1.name) != 2:
                continue
            for level2 in level1.iterdir():
                if level2.is_dir() and not any(level2.iterdir()):
                    with contextlib.suppress(OSError):
                        level2.rmdir()
            if not any(level1.iterdir()):
                with contextlib.suppress(OSError):
                    level1.rmdir()
    except OSError:
        pass


def check_cache_pressure(cache_dir: str | None = None, max_size_mb: int = 500) -> bool:
    """Quick check if cache is over 90% of max size. Used for proactive cleanup."""
    if cache_dir is None:
        from core.paths import cache_path
        cache_dir = str(cache_path("thumbnails"))
    cache = Path(cache_dir)
    if not cache.exists():
        return False
    total = None
    try:
        from core.services_core.cache_index import get_thumbnail_cache_total_size
        from core.services_core.db_api import get_db

        total = get_thumbnail_cache_total_size(get_db())
    except Exception:
        total = None
    if total is None:
        total = 0
        for f in _iter_cache_files(cache):
            try:
                total += f.stat().st_size
            except OSError:
                continue
    threshold = int(max_size_mb * 1024 * 1024 * 0.9)
    return total > threshold
