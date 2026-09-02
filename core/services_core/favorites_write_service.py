"""Write helpers for favorites and collections persistence."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress

_IN_CHUNK_SIZE = 500


def _invalidate_search_caches() -> None:
    with suppress(Exception):
        from core.services_core.db_state_connections import invalidate_readonly_connections

        invalidate_readonly_connections()
    with suppress(Exception):
        from core.search_api.search_page_cache import search_page_cache

        search_page_cache.invalidate()


def _chunks(values: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(values), size):
        yield values[start:start + size]


def insert_favorite_row(
    file_id: int,
    collection_id: int,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    con.execute(
        "INSERT INTO favorites (file_id, collection_id, added_at) VALUES (?, ?, ?)",
        (file_id, collection_id, int(time.time())),
    )
    con.commit()
    _invalidate_search_caches()


def delete_favorite_row(
    file_id: int,
    collection_id: int,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    con.execute(
        "DELETE FROM favorites WHERE file_id=? AND collection_id=?",
        (file_id, collection_id),
    )
    con.commit()
    _invalidate_search_caches()


def batch_insert_favorite_rows(
    file_ids: list[int],
    collection_id: int,
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    now = int(time.time())
    existing = set()
    for chunk in _chunks(file_ids):
        placeholders = ",".join("?" * len(chunk))
        existing_rows = con.execute(
            f"SELECT file_id FROM favorites WHERE file_id IN ({placeholders}) AND collection_id=?",
            list(chunk) + [collection_id],
        ).fetchall()
        existing.update(r[0] for r in existing_rows)

    params = [(fid, collection_id, now) for fid in file_ids if fid not in existing]
    if params:
        con.executemany(
            "INSERT INTO favorites (file_id, collection_id, added_at) VALUES (?, ?, ?)",
            params,
        )
    con.commit()
    if params:
        _invalidate_search_caches()
    return len(params)


def batch_delete_favorite_rows(
    file_ids: list[int],
    collection_id: int | None = None,
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    deleted = 0
    if collection_id is not None:
        for chunk in _chunks(file_ids):
            placeholders = ",".join("?" * len(chunk))
            cur = con.execute(
                f"DELETE FROM favorites WHERE file_id IN ({placeholders}) AND collection_id=?",
                list(chunk) + [collection_id],
            )
            deleted += cur.rowcount
    else:
        for chunk in _chunks(file_ids):
            placeholders = ",".join("?" * len(chunk))
            cur = con.execute(
                f"DELETE FROM favorites WHERE file_id IN ({placeholders})",
                chunk,
            )
            deleted += cur.rowcount
    con.commit()
    if deleted:
        _invalidate_search_caches()
    return deleted


def insert_collection_row(
    name: str,
    query_json: str | None = None,
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    row = con.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM collections").fetchone()
    next_order = row[0] if row else 1
    now = int(time.time())
    cur = con.execute(
        "INSERT INTO collections (name, sort_order, created_at, query_json) VALUES (?, ?, ?, ?)",
        (name, next_order, now, query_json),
    )
    con.commit()
    _invalidate_search_caches()
    return cur.lastrowid


def update_collection_name_row(
    collection_id: int,
    name: str,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    con.execute("UPDATE collections SET name=? WHERE id=?", (name, collection_id))
    con.commit()
    _invalidate_search_caches()


def delete_collection_row(
    collection_id: int,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    con.execute("DELETE FROM favorites WHERE collection_id=?", (collection_id,))
    con.execute("DELETE FROM collections WHERE id=?", (collection_id,))
    con.commit()
    _invalidate_search_caches()


def reorder_collection_rows(
    ids: list[int],
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    for i, cid in enumerate(ids):
        con.execute("UPDATE collections SET sort_order=? WHERE id=?", (i, cid))
    con.commit()
    _invalidate_search_caches()
