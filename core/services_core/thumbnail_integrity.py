"""Thumbnail cache integrity checker.

Detects mismatches where the cached thumbnail is stale relative to its
source file (e.g. the source was edited / replaced after the thumb was
generated). Such stale entries cause the symptom reported in the
2026-04-29 UX audit: a Favorites grid that shows the wrong image
("NO PREVIEW" placeholders, screenshots of editors, unrelated photos).

The check is conservative: it only evicts entries where the on-disk
source file is *strictly newer* than the cached thumbnail file. Missing
sources are handled by the existing cleanup_thumbnail_cache() pass.

NOTE on cache_key shape (corrected after 2026-04-30 review):
``cache_entry.cache_key`` for thumbnails is the basename of the cached
file produced by ``blake2b(f"{file_path}:{mtime}").hexdigest()`` plus an
extension (e.g. ``ab12cd34…ef.webp``). It does **not** encode the
file_id. We therefore read ``file_id`` directly from the column rather
than parsing the key.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


def _cache_root() -> Path:
    from core.paths import cache_path

    return Path(cache_path("thumbnails"))


def _resolve_source_path(con: sqlite3.Connection, file_id: int) -> str | None:
    row = con.execute("SELECT path FROM files WHERE id=? LIMIT 1", (file_id,)).fetchone()
    if not row:
        return None
    p = row[0]
    return str(p) if p else None


def _iter_thumbnail_records(con: sqlite3.Connection) -> Iterator[dict[str, object]]:
    """Like ``list_thumbnail_entry_records`` but also returns ``file_id``.

    Defined locally so we don't have to widen the public cache_index API just
    for the integrity job. Yields records from the DB cursor directly so a
    large thumbnail index is not materialized before the integrity pass starts.
    """
    for r in con.execute(
        "SELECT cache_key, path, file_id FROM cache_entry WHERE kind='thumbnail'"
    ):
        yield {
            "cache_key": str(r[0]),
            "path": str(r[1] or ""),
            "file_id": int(r[2]) if r[2] is not None else None,
        }


def check_thumbnail_integrity(*, max_evict: int = 5000) -> dict[str, int]:
    """Scan thumbnail cache_entry rows and evict stale or orphan thumbs.

    Returns a dict::

        {"checked": N, "stale_evicted": M, "missing_source_evicted": K}

    ``max_evict`` caps the eviction count per run so a corrupted index
    cannot wipe the whole cache in one pass.
    """
    from core.services_core.cache_index import delete_cache_entries
    from core.services_core.db_api import get_db, get_readonly_db
    from core.services_core.db_write import submit_db_write

    using_direct_db = False
    try:
        con = get_readonly_db()
    except RuntimeError:
        # Unit tests often patch only get_db() with an in-memory connection.
        # Production uses readonly for the long stat-heavy scan.
        con = get_db()
        using_direct_db = True

    cache_root = _cache_root()
    stale: list[str] = []
    missing_source: list[str] = []
    checked = 0
    # Map cache_key -> on-disk thumb path so we can unlink after eviction
    # without re-walking the records list.
    thumb_paths: dict[str, Path] = {}

    for rec in _iter_thumbnail_records(con):
        if len(stale) + len(missing_source) >= max_evict:
            break
        checked += 1
        key = str(rec["cache_key"])
        thumb_rel = str(rec["path"])
        file_id = rec["file_id"]
        if not key or not thumb_rel:
            continue
        if not isinstance(file_id, int):
            # Older rows may have NULL file_id — orphan by definition.
            missing_source.append(key)
            continue

        thumb_path = (
            cache_root / thumb_rel if not os.path.isabs(thumb_rel) else Path(thumb_rel)
        )
        thumb_paths[key] = thumb_path
        try:
            thumb_mtime = thumb_path.stat().st_mtime
        except OSError:
            # Already missing on disk — cleanup_thumbnail_cache handles this.
            continue

        source = _resolve_source_path(con, file_id)
        if not source:
            # Orphaned thumb: the source file row is gone.
            missing_source.append(key)
            continue
        try:
            source_mtime = os.stat(source).st_mtime
        except OSError:
            # Source path moved/missing on disk; treat as orphan.
            missing_source.append(key)
            continue

        # Conservative threshold: 2 seconds slack avoids false-positive
        # eviction when filesystem mtime resolution differs slightly between
        # the source and cache filesystems (e.g. SMB / WSL volumes).
        if source_mtime > thumb_mtime + 2.0:
            stale.append(key)

    evicted = stale + missing_source
    if evicted:
        try:
            def _write() -> None:
                wcon = get_db()
                delete_cache_entries(wcon, evicted)
                wcon.commit()

            if using_direct_db:
                _write()
            else:
                submit_db_write(_write)
        except Exception:
            logger.exception(
                "[thumbnail_integrity] failed to delete %d stale entries", len(evicted)
            )
            # Don't unlink on-disk files if the DB delete failed — the
            # entries would re-appear on next run anyway, but pulling the
            # thumbnail file out from under a still-present row would just
            # cause /api/thumbnail/<id> to 404.
            return {
                "checked": checked,
                "stale_evicted": 0,
                "missing_source_evicted": 0,
            }

    # On-disk eviction: only after the DB commit succeeded so we don't
    # leave dangling rows pointing at deleted files.
    for key in evicted:
        thumb_path = thumb_paths.get(key)
        if thumb_path is None:
            continue
        with contextlib.suppress(OSError):
            thumb_path.unlink()

    logger.info(
        "[thumbnail_integrity] checked=%d stale=%d missing_source=%d",
        checked, len(stale), len(missing_source),
    )
    return {
        "checked": checked,
        "stale_evicted": len(stale),
        "missing_source_evicted": len(missing_source),
    }
