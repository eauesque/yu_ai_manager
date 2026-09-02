"""Write helpers for ratings persistence."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def upsert_rating_value(
    file_id: int,
    rating: int,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    now = int(time.time())
    con.execute(
        "INSERT INTO file_ratings (file_id, rating, rated_at, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(file_id) DO UPDATE SET rating=excluded.rating, updated_at=excluded.updated_at",
        (file_id, rating, now, now),
    )
    con.commit()


def delete_rating_value(file_id: int, *, get_db_fn: Callable | None = None) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    con.execute("DELETE FROM file_ratings WHERE file_id=?", (file_id,))
    con.commit()


def upsert_ratings_batch_values(
    items: list[dict[str, Any]],
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    now = int(time.time())

    delete_params = []
    upsert_params = []
    for item in items:
        fid = item["file_id"]
        rating = item["rating"]
        if rating == 0:
            delete_params.append((fid,))
        else:
            upsert_params.append((fid, rating, now, now))

    if delete_params:
        con.executemany(
            "DELETE FROM file_ratings WHERE file_id=?",
            delete_params,
        )
    if upsert_params:
        con.executemany(
            "INSERT INTO file_ratings (file_id, rating, rated_at, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(file_id) DO UPDATE SET rating=excluded.rating, updated_at=excluded.updated_at",
            upsert_params,
        )
    con.commit()
    return len(delete_params) + len(upsert_params)
