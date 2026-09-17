"""Rating filter for search queries."""

from typing import Any


def apply_rating_filter(
    where_parts: list[str],
    params: list[Any],
    min_rating: int | None,
    max_rating: int | None,
) -> bool:
    """Apply rating filter. Returns True if a JOIN on file_ratings is needed."""
    if min_rating is None and max_rating is None:
        return False

    if min_rating is not None and max_rating is not None:
        where_parts.append("rt.rating BETWEEN ? AND ?")
        params.append(min_rating)
        params.append(max_rating)
    elif min_rating is not None:
        where_parts.append("rt.rating >= ?")
        params.append(min_rating)
    else:
        where_parts.append("rt.rating <= ?")
        params.append(max_rating)
    return True
