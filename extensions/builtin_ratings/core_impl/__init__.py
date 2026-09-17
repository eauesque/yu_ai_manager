"""File ratings core logic (1-5 star rating system).

Business logic layer: validation and event emission.
Data access is delegated to store.py.
"""

from core.event_bus import emit
from core.event_bus.event_types import RATING_CLEAR, RATING_SET
from core.search_api.count_cache import count_cache
from core.search_api.search_page_cache import search_page_cache
from core.services_core.store_utils import validate_file_ids

from .store import (
    delete_rating as _store_delete,
)
from .store import (
    get_rating_distribution,
    get_rating_row,
    get_ratings_batch_rows,
)
from .store import (
    upsert_rating as _store_upsert,
)


def _invalidate_search_caches() -> None:
    """Drop cached search payloads/counts affected by rating writes."""
    count_cache.invalidate()
    search_page_cache.invalidate()


def set_rating(file_id: int, rating: int) -> dict:
    """Set or clear a file's rating.

    rating=0 clears the rating (DELETE). 1-5 sets/updates (UPSERT).
    Returns dict with file_id and rating (0 if cleared).
    """
    if rating == 0:
        _store_delete(file_id)
        _invalidate_search_caches()
        emit(RATING_CLEAR, {"file_id": file_id}, source="ratings")
        return {"file_id": file_id, "rating": 0}
    else:
        _store_upsert(file_id, rating)
        _invalidate_search_caches()
        emit(RATING_SET, {"file_id": file_id, "rating": rating}, source="ratings")
        return {"file_id": file_id, "rating": rating}


def set_ratings_batch(items: list) -> dict:
    """Set ratings for multiple files in one transaction.

    Each item: {"file_id": int, "rating": int (0-5)}.
    Returns {"total": N, "succeeded": N, "failed": N, "errors": [...]}.
    """
    succeeded = 0
    errors = []

    # Collect file_ids for validation
    candidate_ids = [
        item.get("file_id") for item in items
        if isinstance(item.get("file_id"), int) and item.get("file_id") > 0
    ]
    existing_ids = validate_file_ids(candidate_ids)

    valid_items = []
    for item in items:
        file_id = item.get("file_id")
        rating = item.get("rating")

        if not isinstance(file_id, int) or file_id <= 0:
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "file_id must be a positive integer"})
            continue
        if not isinstance(rating, int) or rating < 0 or rating > 5:
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "rating must be 0-5"})
            continue
        if file_id not in existing_ids:
            errors.append({"file_id": file_id, "code": "not_found",
                           "error": "File not found"})
            continue
        valid_items.append({"file_id": file_id, "rating": rating})

    if valid_items:
        from .store import upsert_ratings_batch
        succeeded = upsert_ratings_batch(valid_items)
        _invalidate_search_caches()

    return {
        "total": len(items),
        "succeeded": succeeded,
        "failed": len(errors),
        "errors": errors,
    }


def get_rating(file_id: int) -> int:
    """Get a file's rating. Returns 0 if unrated."""
    return get_rating_row(file_id) or 0


def get_ratings_batch(file_ids: list) -> dict:
    """Get ratings for multiple file IDs. Returns dict[int, int] (id -> rating)."""
    return get_ratings_batch_rows(file_ids)


def get_rating_stats() -> dict:
    """Get rating distribution statistics."""
    distribution = get_rating_distribution()
    total = sum(distribution.values())
    return {"total_rated": total, "distribution": distribution}
