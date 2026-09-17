"""Ratings data access layer (Store pattern).

Handles SQL only; contains no business logic.
"""

from __future__ import annotations

from typing import Any, TypeVar

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

T = TypeVar("T")
_IN_CHUNK_SIZE = 500


def _chunks(items: list[T], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def upsert_rating(file_id: int, rating: int) -> None:
    """UPSERT a rating (1-5)."""
    from core.services_core.ratings_write_service import upsert_rating_value

    submit_db_write(lambda: upsert_rating_value(file_id, rating, get_db_fn=get_db))


def delete_rating(file_id: int) -> None:
    """Delete a rating."""
    from core.services_core.ratings_write_service import delete_rating_value

    submit_db_write(lambda: delete_rating_value(file_id, get_db_fn=get_db))


def get_rating_row(file_id: int) -> int | None:
    """Return the rating for a file_id. Returns None if unrated."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT rating FROM file_ratings WHERE file_id=?", (file_id,)
    ).fetchone()
    return row[0] if row else None


def get_ratings_batch_rows(file_ids: list[int]) -> dict[int, int]:
    """Return ratings for multiple file_ids as {file_id: rating}."""
    if not file_ids:
        return {}
    con = get_readonly_db()
    ratings: dict[int, int] = {}
    for chunk in _chunks(file_ids):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT file_id, rating FROM file_ratings WHERE file_id IN ({placeholders})",
            chunk,
        )
        ratings.update({int(r[0]): int(r[1]) for r in cursor})
    return ratings


def upsert_ratings_batch(items: list[dict[str, Any]]) -> int:
    """Batch UPSERT multiple ratings. Returns success count."""
    from core.services_core.ratings_write_service import upsert_ratings_batch_values

    return submit_db_write(
        lambda: upsert_ratings_batch_values(items, get_db_fn=get_db)
    )


def get_rating_distribution() -> dict[int, int]:
    """Return rating distribution as {rating: count}."""
    con = get_readonly_db()
    rows = con.execute(
        "SELECT rating, COUNT(*) FROM file_ratings GROUP BY rating ORDER BY rating"
    )
    return {r[0]: r[1] for r in rows}
