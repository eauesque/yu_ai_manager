"""Cache index operations (atime-independent L2 cache management)."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

THUMB_CACHE_TOUCH_MIN_INTERVAL_SEC = 60


def _now_ts() -> int:
    return int(time.time())


def touch_thumbnail_cache_entry(con: sqlite3.Connection, cache_path: Path, *, file_id: int | None = None) -> None:
    """Create/update thumbnail cache index entry with last_access_at."""
    if not cache_path.exists() or not cache_path.is_file():
        return
    size_bytes = int(cache_path.stat().st_size)
    key = cache_path.name
    ts = _now_ts()
    con.execute(
        """
        INSERT INTO cache_entry(cache_key, kind, path, file_id, size_bytes, last_access_at, updated_at)
        VALUES (?, 'thumbnail', ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          kind='thumbnail',
          path=excluded.path,
          file_id=COALESCE(excluded.file_id, cache_entry.file_id),
          size_bytes=excluded.size_bytes,
          last_access_at=excluded.last_access_at,
          updated_at=excluded.updated_at
        WHERE cache_entry.path IS NOT excluded.path
           OR COALESCE(excluded.file_id, cache_entry.file_id) IS NOT cache_entry.file_id
           OR cache_entry.size_bytes IS NOT excluded.size_bytes
           OR cache_entry.last_access_at IS NULL
           OR cache_entry.last_access_at < (excluded.last_access_at - ?)
        """,
        (key, str(cache_path), file_id, size_bytes, ts, ts, THUMB_CACHE_TOUCH_MIN_INTERVAL_SEC),
    )


def touch_thumbnail_cache_entries_batch_prepared(
    con: sqlite3.Connection,
    rows: Iterable[tuple[str, str, int | None, int]],
) -> int:
    """Like ``touch_thumbnail_cache_entries_batch`` but takes pre-stat'd rows.

    Each row is ``(cache_key, path_str, file_id, size_bytes)``. Caller is
    responsible for having already verified the file exists and computed
    ``size_bytes`` — this lets the disk syscalls run off the single SQLite
    writer thread, which otherwise gets stalled 250-340 ms per batch on
    Windows NTFS holding up every other write (see thumbnail_touch_queue).
    """
    rows_list = [r for r in rows if r and r[0]]
    if not rows_list:
        return 0
    ts = _now_ts()
    con.executemany(
        """
        INSERT INTO cache_entry(cache_key, kind, path, file_id, size_bytes, last_access_at, updated_at)
        VALUES (?, 'thumbnail', ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          kind='thumbnail',
          path=excluded.path,
          file_id=COALESCE(excluded.file_id, cache_entry.file_id),
          size_bytes=excluded.size_bytes,
          last_access_at=excluded.last_access_at,
          updated_at=excluded.updated_at
        WHERE cache_entry.path IS NOT excluded.path
           OR COALESCE(excluded.file_id, cache_entry.file_id) IS NOT cache_entry.file_id
           OR cache_entry.size_bytes IS NOT excluded.size_bytes
           OR cache_entry.last_access_at IS NULL
           OR cache_entry.last_access_at < (excluded.last_access_at - ?)
        """,
        [(key, path, fid, size, ts, ts, THUMB_CACHE_TOUCH_MIN_INTERVAL_SEC) for (key, path, fid, size) in rows_list],
    )
    return len(rows_list)


def touch_thumbnail_cache_entries_batch(
    con: sqlite3.Connection, entries: Iterable[tuple[Path, int | None]]
) -> int:
    """Batch create/update thumbnail cache index entries.

    Returns number of rows attempted (valid existing files only).
    """
    dedup: dict[str, tuple[Path, int | None]] = {}
    for cache_path, file_id in entries:
        if not cache_path.exists() or not cache_path.is_file():
            continue
        dedup[cache_path.name] = (cache_path, file_id)
    if not dedup:
        return 0

    ts = _now_ts()
    rows = []
    for key, (cache_path, file_id) in dedup.items():
        size_bytes = int(cache_path.stat().st_size)
        rows.append((key, str(cache_path), file_id, size_bytes, ts, ts))

    con.executemany(
        """
        INSERT INTO cache_entry(cache_key, kind, path, file_id, size_bytes, last_access_at, updated_at)
        VALUES (?, 'thumbnail', ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          kind='thumbnail',
          path=excluded.path,
          file_id=COALESCE(excluded.file_id, cache_entry.file_id),
          size_bytes=excluded.size_bytes,
          last_access_at=excluded.last_access_at,
          updated_at=excluded.updated_at
        WHERE cache_entry.path IS NOT excluded.path
           OR COALESCE(excluded.file_id, cache_entry.file_id) IS NOT cache_entry.file_id
           OR cache_entry.size_bytes IS NOT excluded.size_bytes
           OR cache_entry.last_access_at IS NULL
           OR cache_entry.last_access_at < (excluded.last_access_at - ?)
        """,
        [(*r, THUMB_CACHE_TOUCH_MIN_INTERVAL_SEC) for r in rows],
    )
    return len(rows)


def delete_cache_entries(con: sqlite3.Connection, keys: Iterable[str]) -> None:
    items = [str(k) for k in keys if str(k)]
    if not items:
        return
    chunk_size = 500
    for start in range(0, len(items), chunk_size):
        chunk = items[start:start + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        con.execute(f"DELETE FROM cache_entry WHERE cache_key IN ({placeholders})", chunk)


def remove_missing_thumbnail_entries(con: sqlite3.Connection, existing_keys: set[str]) -> int:
    stale = [
        str(r[0])
        for r in con.execute("SELECT cache_key FROM cache_entry WHERE kind='thumbnail'")
        if str(r[0]) not in existing_keys
    ]
    if stale:
        delete_cache_entries(con, stale)
    return len(stale)


def get_thumbnail_cache_total_size(con: sqlite3.Connection) -> int | None:
    row = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM cache_entry WHERE kind='thumbnail'"
    ).fetchone()
    if not row or int(row[0] or 0) == 0:
        return None
    return int(row[1] or 0)


def iter_thumbnail_entry_records(con: sqlite3.Connection) -> Iterator[dict[str, int | str]]:
    for r in con.execute(
        "SELECT cache_key, path, size_bytes, last_access_at "
        "FROM cache_entry WHERE kind='thumbnail'"
    ):
        yield {
            "cache_key": str(r[0]),
            "path": str(r[1] or ""),
            "size_bytes": int(r[2]) if r[2] is not None else 0,
            "last_access_at": int(r[3]) if r[3] is not None else 0,
        }


def list_thumbnail_entry_records(con: sqlite3.Connection) -> list[dict[str, int | str]]:
    return list(iter_thumbnail_entry_records(con))


def list_thumbnail_entries(con: sqlite3.Connection) -> dict[str, dict[str, int]]:
    rows = con.execute(
        "SELECT cache_key, size_bytes, last_access_at FROM cache_entry WHERE kind='thumbnail'"
    )
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        key = str(r[0])
        out[key] = {
            "size_bytes": int(r[1]) if r[1] is not None else 0,
            "last_access_at": int(r[2]) if r[2] is not None else 0,
        }
    return out
