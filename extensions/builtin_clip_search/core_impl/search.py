"""Semantic search engine facade."""

import time

from .search_backend import search_vectors
from .search_cache import (
    check_cache_expiry,
    get_cached_search,
    store_cached_search,
)

_MAX_ALLOWED_IDS_CACHE_KEY = 10_000


def semantic_search(
    query: str,
    limit: int = 50,
    threshold: float = 0.2,
    allowed_ids: "set | None" = None,
) -> dict:
    """Search images by text similarity.

    Args:
        query: natural language search text
        limit: max number of results
        threshold: minimum cosine similarity score
        allowed_ids: if provided, only return results whose file_id is in this set

    Returns:
        dict with status, results, metadata
    """
    from .text_encoder import encode_text

    check_cache_expiry()

    cache_key = None
    if not allowed_ids or len(allowed_ids) <= _MAX_ALLOWED_IDS_CACHE_KEY:
        cache_key = (
            query,
            limit,
            threshold,
            frozenset(allowed_ids) if allowed_ids else None,
        )
        cached = get_cached_search(cache_key)
        if cached is not None:
            return cached

    t0 = time.time()
    query_vec = encode_text(query)
    encode_time = time.time() - t0

    raw_results, indexed_count, search_backend, search_time = search_vectors(
        query_vec,
        limit,
        threshold,
        allowed_ids,
    )

    if indexed_count == 0:
        return {
            "status": "empty",
            "total": 0,
            "results": [],
            "query": query,
            "indexed_count": 0,
            "threshold": threshold,
            "timing": {"encode_ms": round(encode_time * 1000, 1)},
        }

    if not raw_results:
        return {
            "status": "empty",
            "total": 0,
            "results": [],
            "query": query,
            "indexed_count": indexed_count,
            "threshold": threshold,
            "timing": {
                "encode_ms": round(encode_time * 1000, 1),
                "search_ms": round(search_time * 1000, 1),
                "backend": search_backend,
            },
        }

    result_ids = [r[0] for r in raw_results]
    from .vector_store import get_file_paths_by_ids
    paths_map = get_file_paths_by_ids(result_ids)

    results = []
    for fid, score in raw_results:
        results.append({
            "file_id": fid,
            "score": round(score, 4),
            "path": paths_map.get(fid, ""),
        })

    result = {
        "status": "ok",
        "total": len(results),
        "results": results,
        "query": query,
        "indexed_count": indexed_count,
        "threshold": threshold,
        "timing": {
            "encode_ms": round(encode_time * 1000, 1),
            "search_ms": round(search_time * 1000, 1),
            "backend": search_backend,
        },
    }

    if cache_key is not None:
        store_cached_search(cache_key, result)
    return result
