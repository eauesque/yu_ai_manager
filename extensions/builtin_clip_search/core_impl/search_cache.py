import logging
import threading
import time
from collections import OrderedDict

import numpy as np

logger = logging.getLogger(__name__)

_faiss = None
try:
    import faiss as _faiss
    logger.info(
        "FAISS %s detected — using accelerated vector search",
        _faiss.__version__ if hasattr(_faiss, "__version__") else "unknown",
    )
except ImportError:
    logger.info("FAISS not installed — falling back to NumPy brute-force search")

_cache_lock = threading.Lock()
_cached_vectors: np.ndarray | None = None  # may be empty when persistent FAISS handled the load
_cached_ids: list | None = None
_faiss_index = None
_cache_last_access: float = 0.0
_search_cache: OrderedDict = OrderedDict()

_CACHE_TTL = 600
_SEARCH_CACHE_MAX = 32
_FAISS_IVF_THRESHOLD = 50_000

_DEFAULT_MODEL = "clip_vit_b_16"


def _empty_vectors_for_model() -> np.ndarray:
    """Return a zero-row, dim-correct array used as a placeholder when the
    full vector matrix is not loaded into RAM (persistent FAISS path)."""
    return np.empty((0, 512), dtype=np.float32)


def ensure_cache(model: str = _DEFAULT_MODEL) -> tuple:
    global _cached_vectors, _cached_ids, _cache_last_access, _faiss_index
    _cache_last_access = time.monotonic()
    if _cached_ids is not None:
        return (_cached_vectors if _cached_vectors is not None else _empty_vectors_for_model()), _cached_ids

    with _cache_lock:
        if _cached_ids is not None:
            return (_cached_vectors if _cached_vectors is not None else _empty_vectors_for_model()), _cached_ids

        # Fast path: try loading the persistent FAISS index from disk via
        # mmap. Skips the ~30 s SQLite read of 1.5 M float16 BLOBs entirely.
        loaded = _try_load_persistent(model)
        if loaded is not None:
            index, ids = loaded
            _faiss_index = index
            _cached_ids = ids
            _cached_vectors = None  # marker: full matrix not in RAM
            _cache_last_access = time.monotonic()
            return _empty_vectors_for_model(), _cached_ids

        # Fallback: cold load from SQLite + build FAISS in memory.
        from .vector_store import load_all_vectors

        t0 = time.time()
        vecs, ids = load_all_vectors(model)
        if vecs.shape[0] > 0:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs = vecs / np.where(norms < 1e-12, 1.0, norms)
        _faiss_index = _try_build_faiss(vecs)
        _cached_vectors = vecs
        _cached_ids = ids
        _cache_last_access = time.monotonic()

        if _faiss_index is not None and vecs.shape[0] > 0:
            try:
                from .faiss_persistence import save_persistent_index
                save_persistent_index(
                    _faiss, _faiss_index, ids, model=model, dim=int(vecs.shape[1]),
                )
            except Exception as exc:
                logger.warning("Failed to persist FAISS index (continuing): %s", exc)

        logger.info(
            "Vector cache loaded: %d vectors in %.2fs (%.1f MB, backend=%s)",
            vecs.shape[0],
            time.time() - t0,
            vecs.nbytes / 1024 / 1024,
            "FAISS" if _faiss_index is not None else "NumPy",
        )
        return _cached_vectors, _cached_ids


def _try_load_persistent(model: str):
    """Try the on-disk FAISS path first; returns ``(index, ids)`` or ``None``."""
    if _faiss is None:
        return None
    try:
        from .faiss_persistence import load_persistent_index
        from .vector_store import count_indexed
    except Exception:
        return None
    try:
        live_count = int(count_indexed(model))
    except Exception:
        live_count = None
    return load_persistent_index(_faiss, model=model, expected_count=live_count)


def check_cache_expiry() -> None:
    global _cached_vectors, _cached_ids, _faiss_index
    if _cached_ids is None or time.monotonic() - _cache_last_access <= _CACHE_TTL:
        return
    with _cache_lock:
        if _cached_ids is None or time.monotonic() - _cache_last_access <= _CACHE_TTL:
            return
        mb = (_cached_vectors.nbytes / 1024 / 1024) if _cached_vectors is not None else 0.0
        _cached_vectors = None
        _cached_ids = None
        _faiss_index = None
        logger.info(
            "Vector cache expired after %ds inactivity (freed %.1f MB; persistent index remains on disk)",
            _CACHE_TTL, mb,
        )


def invalidate_cache() -> None:
    global _cached_vectors, _cached_ids, _cache_last_access, _faiss_index
    with _cache_lock:
        _cached_vectors = None
        _cached_ids = None
        _faiss_index = None
        _cache_last_access = 0.0
        _search_cache.clear()
        # Stale-on-disk index would just be loaded back on the next call; drop
        # it too so callers (reindex / model change) see a clean slate.
        try:
            from .faiss_persistence import delete_persistent_index
            delete_persistent_index(_DEFAULT_MODEL)
        except Exception as exc:
            logger.debug("Failed to delete persistent FAISS index: %s", exc)
    logger.debug("Vector cache invalidated")


def get_cached_search(cache_key):
    if cache_key not in _search_cache:
        return None
    _search_cache.move_to_end(cache_key)
    return _search_cache[cache_key]


def store_cached_search(cache_key, result) -> None:
    _search_cache[cache_key] = result
    if len(_search_cache) > _SEARCH_CACHE_MAX:
        _search_cache.popitem(last=False)


def get_faiss_index():
    return _faiss_index


def _try_build_faiss(vectors: np.ndarray):
    if _faiss is None or vectors.shape[0] == 0:
        return None
    try:
        t0 = time.time()
        index = build_faiss_index(np.ascontiguousarray(vectors, dtype=np.float32))
        logger.info("FAISS index built in %.2fs", time.time() - t0)
        return index
    except Exception as exc:
        logger.warning("FAISS index build failed, using NumPy fallback: %s", exc)
        return None


def build_faiss_index(vectors: np.ndarray):
    n, dim = vectors.shape
    if n < _FAISS_IVF_THRESHOLD:
        index = _faiss.IndexFlatIP(dim)
        index.add(vectors)
        logger.info("FAISS IndexFlatIP built: %d vectors, dim=%d", n, dim)
        return index

    nlist = max(16, int(n ** 0.5))
    nlist = min(nlist, n // 10)
    quantizer = _faiss.IndexFlatIP(dim)
    index = _faiss.IndexIVFFlat(quantizer, dim, nlist, _faiss.METRIC_INNER_PRODUCT)
    index.train(vectors)
    index.add(vectors)
    index.nprobe = max(8, nlist // 10)
    logger.info(
        "FAISS IndexIVFFlat built: %d vectors, dim=%d, nlist=%d, nprobe=%d",
        n,
        dim,
        nlist,
        index.nprobe,
    )
    return index
