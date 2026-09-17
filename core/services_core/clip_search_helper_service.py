"""Writer-side helpers for clip-search helper table maintenance."""

from __future__ import annotations

import threading
from collections.abc import Callable
from importlib import import_module

_state_lock = threading.Lock()
# Start dirty so the first manual-start always rebuilds the helper table.
# We cannot know what file changes occurred between process restarts, so the
# conservative approach (always rebuild once per process lifetime) is correct.
# db_meta persistence was considered but rejected: the rebuild is fast and
# correctness matters more than saving one table-scan per restart.
_helper_table_dirty = True
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def mark_clip_eligible_dirty() -> None:
    """Mark the helper table as needing a refresh before trusted reads."""
    global _helper_table_dirty
    with _state_lock:
        _helper_table_dirty = True


def mark_clip_eligible_clean() -> None:
    """Mark the helper table as synchronized with recent file lifecycle updates."""
    global _helper_table_dirty
    with _state_lock:
        _helper_table_dirty = False


def is_clip_eligible_dirty() -> bool:
    """Return whether the helper table may be stale in this process."""
    with _state_lock:
        return _helper_table_dirty


def refresh_clip_eligible_files_table(
    *,
    get_db_fn: Callable | None = None,
) -> int:
    """Rebuild the clip_eligible_files helper table using a writer DB connection."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    support = import_module("extensions.builtin_clip_search.core_impl.vector_store_support")
    rebuilt = support.rebuild_clip_eligible_files(con)
    mark_clip_eligible_clean()
    return rebuilt


def sync_clip_eligible_file_ids(
    file_ids: list[int],
    *,
    get_db_fn: Callable | None = None,
    mark_clean: bool = False,
) -> int:
    """Incrementally resync helper-table rows for the given file IDs."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    valid_ids = sorted({fid for fid in file_ids if isinstance(fid, int) and fid > 0})
    if not valid_ids:
        return 0

    con = get_db_fn()
    support = import_module("extensions.builtin_clip_search.core_impl.vector_store_support")
    support.ensure_clip_eligible_files_table(con)
    support._ensure_regexp_function(con)

    for chunk in _chunks(valid_ids):
        placeholders = ",".join("?" for _ in chunk)
        con.execute(
            f"DELETE FROM clip_eligible_files WHERE file_id IN ({placeholders})",  # noqa: S608
            chunk,
        )
        con.execute(
            "INSERT INTO clip_eligible_files (file_id)"
            f" SELECT id FROM files WHERE id IN ({placeholders})"  # noqa: S608
            " AND is_deleted = 0"
            " AND lower(path) REGEXP ?"
            " AND path NOT LIKE '%.7z!%'",
            [*chunk, support._CLIP_EXT_RE],
        )
    con.commit()
    if mark_clean:
        mark_clip_eligible_clean()
    total = 0
    for chunk in _chunks(valid_ids):
        placeholders = ",".join("?" for _ in chunk)
        row = con.execute(
            f"SELECT COUNT(*) FROM clip_eligible_files WHERE file_id IN ({placeholders})",  # noqa: S608
            chunk,
        ).fetchone()
        total += row[0] if row else 0
    return total


def delete_clip_eligible_file_ids(
    file_ids: list[int],
    *,
    get_db_fn: Callable | None = None,
    mark_clean: bool = False,
) -> int:
    """Remove helper-table rows for deleted file IDs."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    valid_ids = sorted({fid for fid in file_ids if isinstance(fid, int) and fid > 0})
    if not valid_ids:
        return 0

    con = get_db_fn()
    support = import_module("extensions.builtin_clip_search.core_impl.vector_store_support")
    support.ensure_clip_eligible_files_table(con)

    deleted = 0
    for chunk in _chunks(valid_ids):
        placeholders = ",".join("?" for _ in chunk)
        cur = con.execute(
            f"DELETE FROM clip_eligible_files WHERE file_id IN ({placeholders})",  # noqa: S608
            chunk,
        )
        deleted += cur.rowcount
    con.commit()
    if mark_clean:
        mark_clip_eligible_clean()
    return deleted
