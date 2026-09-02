"""Collection & Favorites API service exports.

Mirrors the layout under ``core/search_api/``: routes layer stays thin and
delegates validation, domain dispatch, and caching to functions under here.
Favorites are grouped here too because they share the ``favorites`` table
with collections (a favorite is just a row keyed by collection_id=1).
"""

from core.collection_api.collections_response import (
    BATCH_ADD_MAX,
    build_create_response,
    build_delete_response,
    build_list_response,
    build_reorder_response,
    build_update_response,
    run_batch_add,
    run_batch_remove,
    validate_batch_payload,
)
from core.collection_api.csv_export import build_collection_csv
from core.collection_api.favorites_response import (
    build_check_collections_response,
    build_check_response,
    build_toggle_response,
    parse_check_args,
    parse_check_collections_args,
)
from core.collection_api.favorites_response import (
    build_list_response as build_favorites_list_response,
)
from core.collection_api.list_cache import invalidate_list, peek_list, put_list

__all__ = [
    "BATCH_ADD_MAX",
    "build_check_collections_response",
    "build_check_response",
    "build_collection_csv",
    "build_create_response",
    "build_delete_response",
    "build_favorites_list_response",
    "build_list_response",
    "build_reorder_response",
    "build_toggle_response",
    "build_update_response",
    "invalidate_list",
    "parse_check_args",
    "parse_check_collections_args",
    "peek_list",
    "put_list",
    "run_batch_add",
    "run_batch_remove",
    "validate_batch_payload",
]
