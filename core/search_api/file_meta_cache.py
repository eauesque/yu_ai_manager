"""In-memory file metadata cache for fast search on large databases."""

import logging
import threading
import time

from .file_meta_cache_build import build_cache_records, get_signature
from .file_meta_cache_query import query_records
from .file_meta_cache_rules import can_use_cache  # noqa: F401  # re-exported

logger = logging.getLogger(__name__)

# Per-thread timing record (see file_meta_cache_query._QR_TLS for rationale).
_ENSURE_TLS = threading.local()


def _ensure_timing() -> dict[str, int]:
    timing = getattr(_ENSURE_TLS, "data", None)
    if timing is None:
        timing = {"sig_ms": 0, "lock_ms": 0, "build_ms": 0}
        _ENSURE_TLS.data = timing
    return timing


def get_last_ensure_timing() -> dict[str, int]:
    """Return per-step timing of the most recent ensure_built() call.

    Lets callers attribute the in-memory cache fast path latency to either the
    DB signature query (slow when contending with the writer thread), the lock
    acquire (slow when a rebuild is in progress), or the actual rebuild.
    """
    return dict(_ensure_timing())
class FileMetaCache:
    """In-memory cache of file metadata for fast search."""

    __slots__ = (
        "_records", "_by_id", "_by_format", "_by_model_family", "_mtime_keys",
        "_signature", "_built_at", "_lock", "_building",
        "_sig_cache", "_sig_cache_at",
    )

    def __init__(self) -> None:
        # Primary: sorted by (mtime DESC, id DESC)
        self._records: list[tuple] = []
        # id -> index in _records
        self._by_id: dict[int, int] = {}
        # Pre-built per-format sorted lists (same sort order as _records)
        self._by_format: dict[str, list[tuple]] = {}
        # Pre-built per-model-family sorted lists (sd / nai / comfy / tensor /
        # unknown). Avoids a 1.6M-row .lower() scan per query when
        # model_filter is set.
        self._by_model_family: dict[str, list[tuple]] = {}
        # Negated mtime keys for bisect (bisect works on ascending order)
        # Stores (-mtime, -id) for binary search on DESC-sorted records
        self._mtime_keys: list[tuple[int, int]] = []
        # (file_count, max_mtime) for invalidation
        self._signature: tuple[int, int] = (0, 0)
        self._built_at: float = 0.0
        self._sig_cache: tuple[int, int] | None = None
        self._sig_cache_at: float = 0.0
        self._lock = threading.RLock()
        self._building = False

    @property
    def ready(self) -> bool:
        return len(self._records) > 0

    @property
    def size(self) -> int:
        return len(self._records)

    def invalidate(self) -> None:
        """Force cache rebuild on next query."""
        with self._lock:
            self._signature = (0, 0)
            self._sig_cache = None
            self._sig_cache_at = 0.0

    def reset_cold(self) -> None:
        """Drop all cached records so the next query falls back to SQL.

        Unlike invalidate() — which only resets the signature and lets the
        stale-but-populated path serve old records while rebuilding in the
        background — this clears the record set entirely.  The next
        ensure_built() call takes the cold-start branch, returns False, and
        the caller falls through to SQL, giving up-to-date results
        immediately instead of waiting ~30 s for the background rebuild.

        Use after Bridge auto-import: a handful of files were just added and
        returning stale search results (missing the new images) would be
        visibly wrong.
        """
        with self._lock:
            self._records = []
            self._by_id = {}
            self._by_format = {}
            self._by_model_family = {}
            self._mtime_keys = []
            self._signature = (0, 0)
            self._sig_cache = None
            self._sig_cache_at = 0.0

    def _get_signature(self, con) -> tuple[int, int]:
        sig, now = get_signature(con, self._sig_cache, self._sig_cache_at)
        self._sig_cache = sig
        self._sig_cache_at = now
        return sig

    def ensure_built(self, con) -> bool:
        """Build cache if stale. Returns True if cache is ready.

        Non-blocking: if another thread is already building, returns
        immediately (stale data or False) so callers can fall back to SQL.

        When the cache is already populated but stale (signature drift after a
        writer batch), the rebuild is dispatched to a daemon thread and the
        request returns stale data immediately. Cold start also dispatches a
        background rebuild and returns False so callers can fall back to SQL
        instead of turning the first search request into an 8+ second cache
        build.
        """
        t0 = time.perf_counter()
        sig = self._get_signature(con)
        t_sig = time.perf_counter()
        _ensure_timing()["sig_ms"] = round((t_sig - t0) * 1000)
        _ensure_timing()["lock_ms"] = 0
        _ensure_timing()["build_ms"] = 0
        if sig == self._signature and self._records:
            return True

        with self._lock:
            t_lock = time.perf_counter()
            _ensure_timing()["lock_ms"] = round((t_lock - t_sig) * 1000)
            if sig == self._signature and self._records:
                return True
            # Stale-but-populated: rebuild in background, serve stale immediately.
            if self._records and not self._building:
                self._building = True
                self._spawn_rebuild()
                return True
            if self._building:
                # Another thread is rebuilding (background or sync); serve
                # whatever we have (could be stale, could be empty on cold).
                return bool(self._records)
            # Cold start: build in the background and let this request use SQL.
            self._building = True
            self._spawn_rebuild()
            return False

    def _spawn_rebuild(self) -> None:
        """Run a cache rebuild on a daemon thread with a fresh readonly DB
        connection. Caller must already hold self._lock and have set
        ``self._building = True``.

        Note: the background thread re-fetches the signature itself so that if
        further writes have landed since the calling thread sampled, the rebuild
        captures the latest snapshot rather than an immediately-stale one.
        """
        def _bg() -> None:
            try:
                from core.services_core.db_api import get_readonly_db
                con = get_readonly_db()
                sig = self._get_signature(con)
                self._build(con, sig)
            except Exception as exc:
                logger.warning("[file_meta_cache] Background rebuild failed: %s", exc)
            finally:
                with self._lock:
                    self._building = False
        threading.Thread(
            target=_bg, daemon=True, name="file_meta_cache-rebuild"
        ).start()

    def is_ready(self) -> bool:
        """Check if cache is built without triggering a build."""
        return bool(self._records)

    def _build(self, con, sig: tuple[int, int]) -> None:
        built = build_cache_records(con, sig)
        with self._lock:
            self._records = built["records"]
            self._by_id = built["by_id"]
            self._by_format = built["by_format"]
            self._by_model_family = built.get("by_model_family", {})
            self._mtime_keys = built["mtime_keys"]
            self._signature = built["signature"]
            self._built_at = built["built_at"]

    def query(
        self,
        sort_by: str = "date",
        file_format: str = "all",
        format_exts: str = "",
        from_ts: int | None = None,
        to_ts: int | None = None,
        in_path: str | None = None,
        min_width: int | None = None,
        max_width: int | None = None,
        min_height: int | None = None,
        max_height: int | None = None,
        model_filter: str = "all",
        limit: int = 100,
        offset: int = 0,
        cursor_mtime: int | None = None,
        cursor_id: int | None = None,
        cursor_direction: str = "desc",
    ) -> tuple[list[dict], int, bool]:
        return query_records(
            self._records,
            self._by_format,
            self._mtime_keys,
            by_model_family=self._by_model_family,
            sort_by=sort_by,
            file_format=file_format,
            format_exts=format_exts,
            from_ts=from_ts,
            to_ts=to_ts,
            in_path=in_path,
            min_width=min_width,
            max_width=max_width,
            min_height=min_height,
            max_height=max_height,
            model_filter=model_filter,
            limit=limit,
            offset=offset,
            cursor_mtime=cursor_mtime,
            cursor_id=cursor_id,
        )

# Global singleton
file_meta_cache = FileMetaCache()
