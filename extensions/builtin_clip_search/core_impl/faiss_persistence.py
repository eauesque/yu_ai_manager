"""Persistent FAISS index for semantic search.

Saves the FAISS index plus its parallel ``file_ids`` array to disk so that
server restarts can ``mmap``-load the vector database in <1 s instead of
re-reading 1.5+ M float16 BLOBs from SQLite (the cold path was ~30 s on
production data).

Layout (under ``<cache_dir>/clip_search/faiss/<model>/``):

* ``index.bin``    — ``faiss.write_index`` output. Loaded via
  ``faiss.read_index(path, faiss.IO_FLAG_MMAP)`` so the kernel pages in
  only the IVF cells touched by each query.
* ``ids.npy``      — ``int64`` array of file_ids parallel to the FAISS
  positional indices (FAISS returns ``0..N-1`` indices, we map them back
  to file ids via this array).
* ``meta.json``    — small validation header. Mismatched
  ``vector_count`` triggers a rebuild on the next ``ensure_cache()``.

The tuple of three files is treated atomically: writes go through ``.tmp``
suffixes and a final rename, and ``load_persistent_index`` only succeeds
when all three are present and consistent.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Bump when the on-disk schema changes in a non-backwards-compatible way.
_SCHEMA_VERSION = 1


def _faiss_root() -> Path:
    from core.paths import cache_path
    return cache_path("clip_search", "faiss")


def get_faiss_dir(model: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in model)
    return _faiss_root() / safe


def get_index_path(model: str) -> Path:
    return get_faiss_dir(model) / "index.bin"


def get_ids_path(model: str) -> Path:
    return get_faiss_dir(model) / "ids.npy"


def get_meta_path(model: str) -> Path:
    return get_faiss_dir(model) / "meta.json"


def _all_present(model: str) -> bool:
    return (
        get_index_path(model).exists()
        and get_ids_path(model).exists()
        and get_meta_path(model).exists()
    )


def save_persistent_index(
    faiss_module,
    index,
    file_ids: list[int],
    *,
    model: str,
    dim: int,
) -> None:
    """Atomically persist ``index`` + ``file_ids`` + meta to disk."""
    target_dir = get_faiss_dir(model)
    target_dir.mkdir(parents=True, exist_ok=True)

    idx_dest = get_index_path(model)
    ids_dest = get_ids_path(model)
    meta_dest = get_meta_path(model)

    idx_tmp = idx_dest.with_suffix(idx_dest.suffix + ".tmp")
    ids_tmp = ids_dest.with_suffix(ids_dest.suffix + ".tmp")
    meta_tmp = meta_dest.with_suffix(meta_dest.suffix + ".tmp")

    t0 = time.time()
    try:
        faiss_module.write_index(index, str(idx_tmp))
        # ``np.save(path, ...)`` silently appends ``.npy`` if the path doesn't
        # already end in it, which clobbers our ``.tmp`` suffix scheme. Use a
        # file handle to bypass that behaviour.
        with open(ids_tmp, "wb") as f:
            np.save(f, np.asarray(file_ids, dtype=np.int64))
        meta = {
            "schema_version": _SCHEMA_VERSION,
            "model": model,
            "dim": dim,
            "vector_count": len(file_ids),
            "faiss_version": getattr(faiss_module, "__version__", "unknown"),
            "saved_at": int(time.time()),
        }
        meta_tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        idx_tmp.replace(idx_dest)
        ids_tmp.replace(ids_dest)
        meta_tmp.replace(meta_dest)

        size_mb = idx_dest.stat().st_size / 1024 / 1024
        logger.info(
            "Persistent FAISS index saved: %s (%.1f MB, %d vectors, %.2f s)",
            idx_dest, size_mb, len(file_ids), time.time() - t0,
        )
    except Exception as exc:
        for tmp in (idx_tmp, ids_tmp, meta_tmp):
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()
        logger.warning("Failed to persist FAISS index: %s", exc)


def load_persistent_index(
    faiss_module,
    *,
    model: str,
    expected_count: int | None = None,
) -> tuple[object, list[int]] | None:
    """Return ``(index, file_ids)`` if a valid on-disk index exists, else None.

    The index is loaded with ``IO_FLAG_MMAP`` so RAM stays low — the kernel
    pages in only the IVF cells touched by each query.

    ``expected_count`` lets callers reject a stale index whose vector count
    no longer matches the live database (caller decides the threshold;
    ``None`` skips the check).
    """
    if not _all_present(model):
        return None

    try:
        meta = json.loads(get_meta_path(model).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read FAISS meta: %s", exc)
        return None

    if meta.get("schema_version") != _SCHEMA_VERSION:
        logger.info(
            "Persistent FAISS index schema mismatch (have=%s, want=%s) — will rebuild",
            meta.get("schema_version"), _SCHEMA_VERSION,
        )
        return None
    if meta.get("model") != model:
        return None

    persisted_count = int(meta.get("vector_count", 0))
    if expected_count is not None:
        # Allow a small drift to avoid rebuilding on every single new vector
        # (rebuild is ~30 s; new vectors trickle in via background indexing).
        # Above this drift, rebuild.
        drift = abs(persisted_count - expected_count)
        if drift > max(1000, expected_count // 100):
            logger.info(
                "Persistent FAISS index is stale: persisted=%d live=%d (drift=%d) — will rebuild",
                persisted_count, expected_count, drift,
            )
            return None

    t0 = time.time()
    try:
        index = faiss_module.read_index(
            str(get_index_path(model)), faiss_module.IO_FLAG_MMAP,
        )
        ids_array = np.load(str(get_ids_path(model)))
    except Exception as exc:
        logger.warning("Failed to mmap-load persistent FAISS index: %s", exc)
        return None

    if int(index.ntotal) != int(ids_array.shape[0]):
        logger.warning(
            "Persistent FAISS index ntotal=%d != ids count=%d — corrupt, will rebuild",
            int(index.ntotal), int(ids_array.shape[0]),
        )
        return None

    file_ids = ids_array.tolist()
    logger.info(
        "Persistent FAISS index loaded via mmap: %d vectors in %.2f s (saved %.0f s ago)",
        index.ntotal, time.time() - t0,
        max(0, time.time() - meta.get("saved_at", 0)),
    )
    return index, file_ids


def delete_persistent_index(model: str) -> None:
    """Remove all on-disk index artifacts (caller is reindexing or invalidating)."""
    for path in (get_index_path(model), get_ids_path(model), get_meta_path(model)):
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Failed to delete %s: %s", path, exc)
