"""Thumbnail batch warmup core -- orchestration, locking, background launch.

Coordinates batch thumbnail generation for container views by grouping
file IDs into archive buckets and dispatching to format-specific warmup
functions.
"""

import logging
import threading

logger = logging.getLogger(__name__)

# Per-archive lock: prevent concurrent processing of the same archive
_archive_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()
_ARCHIVE_LOCKS_MAX = 500
_IN_CHUNK_SIZE = 500

# Track active warmups (prevent duplicate launches)
_active_warmups: set = set()

# CV for per-archive warmup completion notification (independent of _archive_locks)
_archive_done_cv_lock: threading.Lock = threading.Lock()
_archive_done_cvs: dict[str, threading.Condition] = {}


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _get_archive_lock(archive_path: str) -> threading.Lock:
    """Acquire or create a per-archive lock (bounded to prevent unbounded growth)."""
    with _lock_guard:
        # Prevent unbounded growth of unused entries: evict unlocked entries when over limit
        if len(_archive_locks) >= _ARCHIVE_LOCKS_MAX and archive_path not in _archive_locks:
            stale = [k for k, v in _archive_locks.items() if not v.locked()]
            for k in stale:
                del _archive_locks[k]
        if archive_path not in _archive_locks:
            _archive_locks[archive_path] = threading.Lock()
        return _archive_locks[archive_path]


def _cleanup_archive_lock(archive_path: str) -> None:
    """Remove a per-archive lock entry after processing."""
    with _lock_guard:
        _archive_locks.pop(archive_path, None)


def warmup_thumbnails_for_ids(file_ids: list[int]) -> int:
    """Generate thumbnails in batch for the given file IDs.

    Groups archive members by archive path and opens each archive
    only once for all its members.

    Returns:
        Number of thumbnails generated.
    """
    from core.services_core.db_api import get_readonly_db

    if not file_ids:
        return 0

    # Fetch path info from DB (batch split to respect SQLite 999 variable limit)
    con = get_readonly_db()
    rows = []
    for batch in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in batch)
        rows.extend(con.execute(
            f"SELECT id, path, mtime FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
            batch,
        ))

    if not rows:
        return 0

    from .thumbnail_common import cache_path_for_source, ensure_thumbnail_cache_dir

    cache_dir = ensure_thumbnail_cache_dir()

    # Exclude already cached & group by archive
    # Tuple: (file_id, inner_path, full_path, mtime)
    archive_groups: dict[str, list[tuple[int, str, str, object]]] = {}
    plain_files: list[tuple[int, str]] = []

    for row in rows:
        file_path_str = row["path"]
        file_mtime = row["mtime"]
        cp = cache_path_for_source(cache_dir, file_path_str, file_mtime)
        if cp.exists():
            continue  # Already cached

        from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path

        if is_archive_member(file_path_str):
            archive_path, inner_path = split_archive_path(file_path_str)
            archive_groups.setdefault(archive_path, []).append(
                (row["id"], inner_path, file_path_str, file_mtime)
            )
        else:
            plain_files.append((row["id"], file_path_str))

    generated = 0

    # Batch process per archive
    from .thumbnail_batch_warmup_archives import _warmup_7z, _warmup_rar, _warmup_zip

    for archive_path, members in archive_groups.items():
        try:
            if archive_path.lower().endswith(".7z"):
                generated += _warmup_7z(archive_path, members, cache_dir)
            elif archive_path.lower().endswith(".rar"):
                generated += _warmup_rar(archive_path, members, cache_dir)
            else:
                generated += _warmup_zip(archive_path, members, cache_dir)
        except Exception as exc:
            logger.warning("Batch warmup failed for %s: %s", archive_path, exc)

    # Use existing serve_thumbnail for regular files
    if plain_files:
        generated += _warmup_plain(plain_files)

    return generated


def _warmup_plain(files: list[tuple[int, str]]) -> int:
    """Generate thumbnails for regular (non-archive) files."""
    from .thumbnail import serve_thumbnail

    count = 0
    for file_id, _ in files:
        try:
            serve_thumbnail(file_id)
            count += 1
        except Exception:
            logger.debug("file metadata step failed", exc_info=True)
    return count


def start_warmup_background(file_ids: list[int]) -> bool:
    """Start warmup in a background thread.

    Prevents duplicate launches for the same set of IDs.

    Returns:
        True if started, False if already running for these IDs.
    """
    # Simple dedup check: hash of sorted ID tuple
    key = hash(tuple(sorted(file_ids[:100])))  # Determined by first 100 entries
    if key in _active_warmups:
        return False

    _active_warmups.add(key)

    def _run():
        try:
            generated = warmup_thumbnails_for_ids(file_ids)
            logger.info("Background warmup done: %d thumbnails generated", generated)
        except Exception as exc:
            logger.warning("Background warmup error: %s", exc)
        finally:
            _active_warmups.discard(key)

    t = threading.Thread(target=_run, name="thumb-warmup", daemon=True)
    t.start()
    return True
