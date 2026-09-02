"""Status and index management routes for Hailo semantic search."""

import logging
import threading
import time as time_mod

from quart import jsonify, request

from .hailo_semantic_search_common import ext_config

logger = logging.getLogger(__name__)


_sem_count_cache: dict = {"indexed": 0, "unindexed": 0, "ts": 0, "indexed_ts": 0}
# count_indexed scans file_vectors (3-4s on production-scale vectors.db).
# v4.134.7: extended TTL with explicit invalidate at indexing finish so the
# UI does not see stale counts. Same pattern as hailo-yolo v4.134.5.
_INDEXED_TTL_S = 300  # was 30
_UNINDEXED_TTL_S = 300


def invalidate_sem_count_cache() -> None:
    """Drop the cached indexed/unindexed counts. Called by _finish_indexing
    so the next /api/status poll reflects post-indexing values instead of
    returning a 5-minute-fresh stale snapshot."""
    _sem_count_cache["indexed_ts"] = 0
    _sem_count_cache["ts"] = 0


_sem_warmup_started = False
_sem_warmup_lock = threading.Lock()


def _warmup_sem_count_cache() -> None:
    """Cold-start warm-up so the first /api/status poll does not pay the
    3-4s count_indexed scan."""
    try:
        from core.clip_core.vector_store import count_indexed, count_unindexed

        _sem_count_cache["indexed"] = count_indexed()
        _sem_count_cache["indexed_ts"] = time_mod.monotonic()
        _sem_count_cache["unindexed"] = count_unindexed()
        _sem_count_cache["ts"] = time_mod.monotonic()
    except Exception:
        logger.debug("semantic count cache warm-up skipped", exc_info=True)


def _ensure_sem_warmup() -> None:
    global _sem_warmup_started
    with _sem_warmup_lock:
        if _sem_warmup_started:
            return
        _sem_warmup_started = True
    threading.Thread(
        target=_warmup_sem_count_cache, daemon=True, name="sem-count-warmup"
    ).start()


async def _get_sem_runtime_payload() -> dict:
    from core.clip_core.encoder_factory import get_encoder_info
    from core.clip_core.vector_store import count_indexed

    encoder_info = get_encoder_info()
    now = time_mod.monotonic()
    if now - _sem_count_cache["indexed_ts"] > _INDEXED_TTL_S:
        _sem_count_cache["indexed_ts"] = now

        def _bg_count_indexed():
            try:
                _sem_count_cache["indexed"] = count_indexed()
            except Exception:
                logger.debug("semantic indexed count skipped", exc_info=True)

        threading.Thread(
            target=_bg_count_indexed, daemon=True, name="sem-indexed-count"
        ).start()
    indexed = _sem_count_cache["indexed"]
    if now - _sem_count_cache["ts"] > _UNINDEXED_TTL_S:
        _sem_count_cache["ts"] = now

        def _bg_count():
            try:
                from core.clip_core.vector_store import count_unindexed
                _sem_count_cache["unindexed"] = count_unindexed()
            except Exception:
                logger.warning("hailo_semantic_search_status_routes.py: step failed", exc_info=True)

        threading.Thread(target=_bg_count, daemon=True, name="sem-count").start()

    return {
        "status": "ok",
        "indexed_count": indexed,
        "unindexed_count": _sem_count_cache.get("unindexed", 0),
        "backends": encoder_info["backends"],
        "auto_index_on_scan": ext_config("auto_index_on_scan", False),
        "preferred_backend": ext_config("preferred_backend", "auto"),
    }


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_status_routes(bp):
    _ensure_sem_warmup()

    @bp.route("/api/runtime")
    @bp.route("/api/status")
    async def api_runtime():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        return jsonify(await _get_sem_runtime_payload())

    @bp.route("/api/backends")
    async def api_backends():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.clip_core.encoder_factory import get_encoder_info
        return jsonify(get_encoder_info())

    @bp.route("/api/index/start", methods=["POST"])
    async def api_index_start():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.clip_core.encoder_factory import get_best_encoder
        from core.clip_core.indexer import start_indexing

        data = await request.get_json(silent=True) or {}
        batch_size = data.get("batch_size", ext_config("batch_size", 32))
        preferred = data.get("backend", ext_config("preferred_backend", "auto"))
        distributed = data.get("distributed", False)

        def _factory():
            return get_best_encoder(preferred=preferred)

        return jsonify(start_indexing(
            batch_size=int(batch_size),
            encoder_factory=_factory,
            preprocess_fn=None,
            distributed=distributed,
            preflight=False,
        ))

    @bp.route("/api/index/status")
    async def api_index_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.clip_core.indexer import get_index_status
        return jsonify(get_index_status())

    @bp.route("/api/index/stop", methods=["POST"])
    async def api_index_stop():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.clip_core.indexer import stop_indexing
        return jsonify(stop_indexing())

    @bp.route("/api/index/clear", methods=["POST"])
    async def api_index_clear():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.clip_core.search import invalidate_cache
        from core.clip_core.vector_store import delete_all_vectors
        deleted = delete_all_vectors()
        invalidate_cache()
        return jsonify({"status": "ok", "deleted": deleted})
