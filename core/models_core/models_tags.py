"""DB CRUD for tags and file_tags tables."""

import sqlite3
from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Tag ID cache — eliminate repeated SELECTs for the same tag during scan
# ---------------------------------------------------------------------------
# key: (namespace, tag) -> value: (tag_id, first_seen_mtime)
_tag_cache: dict[tuple, tuple] = {}

_TAG_CACHE_MAX = 100_000


def reset_tag_cache() -> None:
    """Clear cache at scan start."""
    _tag_cache.clear()


def clear_tags_for_file(con: sqlite3.Connection, file_id: int) -> None:
    """Delete only meta tags on rescan, preserving user tags."""
    con.execute(
        "DELETE FROM file_tags WHERE file_id=? AND source='meta'", (file_id,)
    )


def clear_tags_for_files_batch(
    con: sqlite3.Connection, file_ids: Sequence[int]
) -> None:
    """Batch delete meta tags for multiple files."""
    if not file_ids:
        return
    chunk_size = 900
    for i in range(0, len(file_ids), chunk_size):
        chunk = file_ids[i : i + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        con.execute(
            f"DELETE FROM file_tags WHERE file_id IN ({placeholders}) AND source='meta'",
            chunk,
        )


def upsert_tag(
    con: sqlite3.Connection,
    namespace: str | None,
    tag: str,
    *,
    first_seen_mtime: int | None = None,
) -> int:
    """Get or create a tag row, returning its id.

    Uses an in-memory cache to avoid repeated SELECT for the same tag.
    Falls back to SELECT-first to handle NULL namespace correctly
    (ON CONFLICT(tag, namespace) does not fire when namespace is NULL).
    """
    key = (namespace, tag)
    cached = _tag_cache.get(key)
    if cached is not None:
        tag_id, cached_mtime = cached
        # MIN update for first_seen_mtime (update DB if an older value exists)
        if first_seen_mtime is not None and (
            cached_mtime is None or first_seen_mtime < cached_mtime
        ):
            cur = con.execute(
                """
                UPDATE tags
                SET first_seen_mtime=?
                WHERE id=?
                  AND (first_seen_mtime IS NULL OR first_seen_mtime>?)
                """,
                (first_seen_mtime, tag_id, first_seen_mtime),
            )
            if cur.rowcount:
                _tag_cache[key] = (tag_id, first_seen_mtime)
        return tag_id

    # Cache miss — SELECT first (NULL namespace safe)
    row = con.execute(
        "SELECT id, first_seen_mtime FROM tags WHERE tag=? AND namespace IS ?",
        (tag, namespace),
    ).fetchone()
    if row:
        tag_id = int(row[0])
        existing_mtime = row[1]
        if first_seen_mtime is not None and (existing_mtime is None or first_seen_mtime < existing_mtime):
            cur = con.execute(
                """
                    UPDATE tags
                    SET first_seen_mtime=?
                    WHERE id=?
                      AND (first_seen_mtime IS NULL OR first_seen_mtime>?)
                    """,
                (first_seen_mtime, tag_id, first_seen_mtime),
            )
            if cur.rowcount:
                existing_mtime = first_seen_mtime
        if len(_tag_cache) < _TAG_CACHE_MAX:
            _tag_cache[key] = (tag_id, existing_mtime)
        return tag_id

    # New tag — INSERT
    con.execute(
        "INSERT INTO tags(tag, namespace, first_seen_mtime) VALUES(?,?,?)",
        (tag, namespace, first_seen_mtime),
    )
    tag_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
    if len(_tag_cache) < _TAG_CACHE_MAX:
        _tag_cache[key] = (tag_id, first_seen_mtime)
    return tag_id


def insert_file_tag(
    con: sqlite3.Connection,
    file_id: int,
    tag_id: int,
    weight: float,
    source: str = "meta",
) -> None:
    con.execute(
        """INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(?,?,?,?)
           ON CONFLICT(file_id, tag_id) DO UPDATE SET weight=excluded.weight,
             source = CASE WHEN excluded.source = 'user' THEN 'user'
                           ELSE file_tags.source END
           WHERE file_tags.weight IS NOT excluded.weight
              OR (
                CASE WHEN excluded.source = 'user' THEN 'user'
                     ELSE file_tags.source END
              ) IS NOT file_tags.source
        """,
        (file_id, tag_id, weight, source),
    )


def insert_file_tags_batch(
    con: sqlite3.Connection,
    rows: Sequence[tuple[int, int, float, str]],
) -> None:
    """Batch INSERT file_tags using executemany.

    rows: [(file_id, tag_id, weight, source), ...]
    """
    if not rows:
        return
    con.executemany(
        """INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(?,?,?,?)
           ON CONFLICT(file_id, tag_id) DO UPDATE SET weight=excluded.weight,
             source = CASE WHEN excluded.source = 'user' THEN 'user'
                           ELSE file_tags.source END
           WHERE file_tags.weight IS NOT excluded.weight
              OR (
                CASE WHEN excluded.source = 'user' THEN 'user'
                     ELSE file_tags.source END
              ) IS NOT file_tags.source
        """,
        rows,
    )
