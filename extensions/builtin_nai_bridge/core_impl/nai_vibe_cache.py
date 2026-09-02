"""File-based cache for NAI V4 encode-vibe results.

NAI's /ai/encode-vibe charges 2 Anlas per call and locks the
information_extracted value into the encoded blob. Re-encoding the
same (image, model, info_extracted) triple every generation wastes
Anlas, so we persist the binary response under

    <data_dir>/nai_vibe_cache/<sha>__<model>__<info>.bin

Each hit os.utime()s the file to keep LRU prune accurate. Prune runs
on a background thread to avoid blocking the generate path.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import uuid
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# -- Allow-list --------------------------------------------------------
# Model strings outside this set collapse to "other" in cache keys so
# attacker-controlled model strings (e.g. from .naiv4vibe files) can't
# fragment the cache namespace or cause path issues.
_KNOWN_MODELS = frozenset({
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated-preview",
})

# -- Key locks (per-triple in-process) --------------------------------
# Prevents two concurrent encode_vibe() calls for the same key from
# both paying 2 Anlas. Uses RLock so the same thread can nest safely.
# WeakValueDictionary: once no call-stack holds a reference to the lk
# object it is GC'd automatically, preventing unbounded growth when
# many distinct images are processed over a long session.
_KEY_LOCKS: weakref.WeakValueDictionary[str, threading.RLock] = (
    weakref.WeakValueDictionary()
)
_KEY_LOCKS_GUARD = threading.Lock()

# -- Prune state -------------------------------------------------------
_PRUNE_LOCK = threading.Lock()
_PRUNE_THREAD: threading.Thread | None = None


# -- Helpers -----------------------------------------------------------

def _cache_dir() -> Path:
    """Return the cache root; create on first use."""
    # Lazy import avoids circular deps at module load time.
    from core.paths import get_data_dir
    root = get_data_dir() / "nai_vibe_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_model(model: str) -> str:
    return model if model in _KNOWN_MODELS else "other"


# -- Public API --------------------------------------------------------

def cache_key(image_bytes: bytes, model: str, info_extracted: float) -> str:
    """Return the canonical cache filename for the (image, model, info) triple.

    Raises ValueError if info_extracted is outside [0.0, 1.0].
    """
    info = float(info_extracted)
    if not (0.0 <= info <= 1.0):
        raise ValueError(f"info_extracted out of range: {info_extracted!r}")
    sha = hashlib.sha256(image_bytes).hexdigest()
    return f"{sha}__{_safe_model(model)}__{info:.2f}.bin"


def get_cached(
    image_bytes: bytes, model: str, info_extracted: float,
) -> bytes | None:
    """Return raw vibe binary if cached, else None.

    Updates mtime on hit so the LRU prune can track recency.
    """
    try:
        key = cache_key(image_bytes, model, info_extracted)
    except ValueError:
        return None
    p = _cache_dir() / key
    if not p.exists():
        return None
    try:
        data = p.read_bytes()
        os.utime(p, None)  # LRU touch
        return data
    except OSError as exc:
        logger.warning("nai_vibe_cache read failed: %s", exc)
        return None


def put(
    image_bytes: bytes,
    model: str,
    info_extracted: float,
    vibe_blob: bytes,
) -> None:
    """Atomically store vibe_blob (write to .tmp, then os.replace).

    Uses thread id + uuid in the tmp name so two concurrent puts for
    the same key from the same process never collide on the .tmp file.
    """
    p = _cache_dir() / cache_key(image_bytes, model, info_extracted)
    tmp_name = (
        f"{p.stem}.{os.getpid()}"
        f".{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp"
    )
    tmp = p.with_name(tmp_name)
    try:
        tmp.write_bytes(vibe_blob)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            import contextlib
            with contextlib.suppress(OSError):
                tmp.unlink()


@contextmanager
def key_lock(
    image_bytes: bytes, model: str, info_extracted: float,
) -> Iterator[None]:
    """Context manager holding a per-key RLock.

    Prevents two concurrent encode_vibe() calls for the same
    (image, model, info_extracted) triple from both paying 2 Anlas.
    RLock so the same thread can nest (test fixtures / retry paths).
    """
    try:
        key = cache_key(image_bytes, model, info_extracted)
    except ValueError:
        # Out-of-range info → just yield without locking
        yield
        return
    with _KEY_LOCKS_GUARD:
        lk = _KEY_LOCKS.get(key)
        if lk is None:
            lk = threading.RLock()
            _KEY_LOCKS[key] = lk
    with lk:
        yield


def _prune_sync(max_size_mb: float = 500.0) -> None:
    """LRU prune: evict oldest files until total size <= max_size_mb."""
    root = _cache_dir()
    budget = int(max_size_mb * 1024 * 1024)
    entries: list[tuple[float, int, Path]] = []
    for p in root.glob("*.bin"):
        try:
            st = p.stat()
            entries.append((st.st_mtime, st.st_size, p))
        except OSError:
            continue
    entries.sort(key=lambda e: e[0])  # oldest first
    total = sum(e[1] for e in entries)
    while total > budget and entries:
        _, sz, p = entries.pop(0)
        try:
            p.unlink()
            total -= sz
        except OSError as exc:
            logger.warning("nai_vibe_cache prune failed for %s: %s", p, exc)


def prune_async(max_size_mb: float = 500.0) -> None:
    """Schedule a background LRU prune. No-op if one is already running."""
    global _PRUNE_THREAD
    with _PRUNE_LOCK:
        if _PRUNE_THREAD is not None and _PRUNE_THREAD.is_alive():
            return

        def _runner() -> None:
            try:
                _prune_sync(max_size_mb)
            except Exception:
                logger.exception("nai_vibe_cache prune crashed")

        _PRUNE_THREAD = threading.Thread(
            target=_runner, name="nai-vibe-cache-prune", daemon=True,
        )
        _PRUNE_THREAD.start()
