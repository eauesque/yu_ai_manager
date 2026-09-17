import time

import numpy as np

from .search_cache import ensure_cache, get_faiss_index


def search_vectors(
    query_vec: np.ndarray,
    limit: int,
    threshold: float,
    allowed_ids: "set | None" = None,
) -> tuple[list, int, str, float]:
    vectors, file_ids = ensure_cache()

    # When the persistent FAISS path served the cache, vectors is an empty
    # placeholder and the actual count lives on the FAISS index.
    faiss_index = get_faiss_index()
    indexed_count = int(faiss_index.ntotal) if faiss_index is not None else vectors.shape[0]

    if indexed_count == 0:
        return [], indexed_count, "empty", 0.0

    t0 = time.time()
    if faiss_index is not None:
        results = _search_faiss(faiss_index, query_vec, limit, threshold, file_ids, allowed_ids)
        return results, indexed_count, "faiss", time.time() - t0
    results = _search_numpy(query_vec, limit, threshold, vectors, file_ids, allowed_ids)
    return results, indexed_count, "numpy", time.time() - t0


def _search_faiss(
    index,
    query_vec: np.ndarray,
    limit: int,
    threshold: float,
    file_ids: list,
    allowed_ids: "set | None" = None,
) -> list:
    query = np.ascontiguousarray(query_vec.reshape(1, -1), dtype=np.float32)
    k = min(limit * (4 if allowed_ids else 2), int(index.ntotal))
    scores, indices = index.search(query, k)
    results = []
    for score, idx in zip(scores[0], indices[0], strict=False):
        if idx < 0 or score < threshold:
            continue
        fid = file_ids[idx]
        if allowed_ids is not None and fid not in allowed_ids:
            continue
        results.append((fid, float(score)))
        if len(results) >= limit:
            break
    return results


def _search_numpy(
    query_vec: np.ndarray,
    limit: int,
    threshold: float,
    vectors: np.ndarray,
    file_ids: list,
    allowed_ids: "set | None" = None,
) -> list:
    similarities = vectors @ query_vec
    mask = similarities >= threshold
    if allowed_ids is not None:
        id_mask = np.array([fid in allowed_ids for fid in file_ids], dtype=bool)
        mask = mask & id_mask
    if not np.any(mask):
        return []
    filtered_scores = similarities[mask]
    filtered_indices = np.where(mask)[0]
    top_order = np.argsort(filtered_scores)[::-1][:limit]
    top_indices = filtered_indices[top_order]
    top_scores = filtered_scores[top_order]
    return [(file_ids[i], float(s)) for i, s in zip(top_indices, top_scores, strict=False)]
