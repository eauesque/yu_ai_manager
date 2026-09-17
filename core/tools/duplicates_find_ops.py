"""Duplicate search helpers."""

from typing import Any

from core.services_core.db_api import get_raw_db
from core.tools.duplicates_find_format import build_groups, filter_cross_directory
from core.tools.duplicates_find_query import build_hash_stats, query_duplicate_rows

# Cap groups returned to UI; rendering thousands of groups crashes the browser.
GROUP_LIMIT = 200


def find_duplicates(cross_directory: bool, method: str, threshold: int) -> tuple[dict[str, Any], int]:
    con = get_raw_db()
    rows = query_duplicate_rows(con, method, threshold)
    if rows is None:
        return {"error": "Invalid method"}, 400

    rows = filter_cross_directory(rows, method, cross_directory)

    groups, total_duplicates = build_groups(rows, method)
    total_groups = len(groups)
    truncated = total_groups > GROUP_LIMIT
    return {
        "groups": groups[:GROUP_LIMIT],
        "total_duplicates": total_duplicates,
        "method": method,
        "hash_stats": build_hash_stats(),
        "truncated": truncated,
        "group_limit": GROUP_LIMIT,
        "total_groups": total_groups,
    }, 200
