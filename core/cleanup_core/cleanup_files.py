"""File/path cleanup helpers."""

import logging
import sqlite3
from pathlib import Path

from core.platform import normalize_path

logger = logging.getLogger(__name__)

# SQLite SQLITE_MAX_VARIABLE_NUMBER default is 999; chunk to stay safe
_CHUNK_SIZE = 500


def _chunked_in_execute(
    con: sqlite3.Connection,
    sql_before_in: str,
    sql_after_in: str,
    ids: list[int],
    extra_params: tuple = (),
) -> None:
    """Safely execute SQL containing an IN clause by splitting into chunks.

    Builds the form: sql_before_in + " IN (" + placeholders + ")" + sql_after_in.
    Dynamically generates only placeholders without using .format() on the SQL template.
    """
    for i in range(0, len(ids), _CHUNK_SIZE):
        chunk = ids[i: i + _CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        sql = f"{sql_before_in} IN ({placeholders}){sql_after_in}"
        con.execute(sql, list(chunk) + list(extra_params))


def cleanup_dedupe_paths(con: sqlite3.Connection, dry_run: bool = False) -> int:
    """Deduplicate rows with canonically identical files.path."""
    bucket: dict[str, tuple[int, int]] = {}
    dup_ids: list[int] = []

    for fid, path, mtime in con.execute("SELECT id, path, mtime FROM files"):
        canonical = normalize_path(Path(str(path)))
        fid_i = int(fid)
        mt_i = int(mtime)
        if canonical not in bucket:
            bucket[canonical] = (fid_i, mt_i)
        else:
            keep_id, keep_m = bucket[canonical]
            if mt_i > keep_m:
                dup_ids.append(keep_id)
                bucket[canonical] = (fid_i, mt_i)
            else:
                dup_ids.append(fid_i)

    if not dup_ids:
        return 0
    if dry_run:
        return len(dup_ids)

    _chunked_in_execute(con, "DELETE FROM templates WHERE file_id", "", dup_ids)
    _chunked_in_execute(con, "DELETE FROM file_tags WHERE file_id", "", dup_ids)
    _chunked_in_execute(con, "DELETE FROM files WHERE id", "", dup_ids)
    return len(dup_ids)


def cleanup_prune_unused_tags(con: sqlite3.Connection, dry_run: bool = False) -> int:
    row = con.execute(
        "SELECT COUNT(*) FROM tags t LEFT JOIN file_tags ft ON t.id = ft.tag_id"
        " WHERE ft.tag_id IS NULL"
    ).fetchone()
    n = int(row[0]) if row else 0
    if n <= 0:
        return 0
    if dry_run:
        return n
    con.execute(
        "DELETE FROM tags WHERE id IN"
        " (SELECT t.id FROM tags t LEFT JOIN file_tags ft ON t.id = ft.tag_id"
        " WHERE ft.tag_id IS NULL)"
    )
    return n


def cleanup_mark_missing_files(con: sqlite3.Connection, dry_run: bool = False) -> int:
    missing: list[int] = []
    for fid, path, is_del in con.execute("SELECT id, path, is_deleted FROM files"):
        if int(is_del) == 1:
            continue
        if not Path(str(path)).exists():
            missing.append(int(fid))

    if not missing:
        return 0
    if dry_run:
        return len(missing)

    _chunked_in_execute(
        con, "UPDATE files SET is_deleted=1 WHERE id", "", missing
    )
    # Invalidate in-memory search cache
    try:
        from core.query.tag_resolve_cache import path_match_probe_cache, tag_resolve_cache
        from core.search_api.file_meta_cache import file_meta_cache
        from core.search_api.search_page_cache import search_page_cache
        file_meta_cache.invalidate()
        tag_resolve_cache.invalidate()
        path_match_probe_cache.invalidate()
        search_page_cache.invalidate()
    except Exception:
        logger.warning("step failed", exc_info=True)
    return len(missing)
