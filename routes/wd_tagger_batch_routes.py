"""Batch and stats routes for WD-Tagger."""

import logging
import threading

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.services_core.db_async import run_db_sync
from routes.wd_tagger_route_utils import parse_bool_field, parse_int_field

logger = logging.getLogger(__name__)

# /api/wd-tagger/stats: 5 つの COUNT/COUNT(DISTINCT)/GROUP BY を file_wd_tags に
# 連打して 2.5〜3 秒かかる。値を更新する経路は限定的 (run_batch_tagging の完了点
# と delete_wd_tags_*) なので、書き込み完了時に明示 invalidate して TTL は長く取る。
# yolo の v4.134.5 と同じ SWR + invalidate パターン。
_WT_STATS_CACHE = SimpleTTLCache(ttl_seconds=300.0)

_wt_stats_warmup_started = False
_wt_stats_warmup_lock = threading.Lock()
# Stored at register_batch_routes time so invalidate can trigger bg refresh
# without needing the importer passed in.
_wt_importer_ref = None


def invalidate_wt_stats_cache() -> None:
    """Drop the cached /api/wd-tagger/stats payload and kick off a background
    refresh so the next UI poll doesn't pay the 30-40s aggregate cost.

    Called from batch_ops on WD_TAGGER_COMPLETE and from delete paths.
    """
    _WT_STATS_CACHE.invalidate()
    importer = _wt_importer_ref
    if importer is not None:
        threading.Thread(
            target=_warmup_wt_stats_cache,
            args=(importer,),
            daemon=True,
            name="wt-stats-refresh",
        ).start()


def _warmup_wt_stats_cache(wt_importer) -> None:
    """Recompute WD-Tagger stats and persist to both the in-memory TTL cache
    and the DB-backed wd_tag_stats_cache table (Migration 77).

    Persisting to DB means the next server restart finds pre-computed stats
    immediately instead of paying the 30-40s aggregate cost on cold start.
    """
    try:
        store_mod = wt_importer("store")
        get_wd_tag_stats = store_mod.get_wd_tag_stats
        count_untagged_unknown_files = store_mod.count_untagged_unknown_files
        save_wd_tag_stats_cache = store_mod.save_wd_tag_stats_cache
        stats = get_wd_tag_stats()
        stats["untagged_unknown"] = count_untagged_unknown_files()
        _WT_STATS_CACHE.put("payload", stats)
        # Persist to DB so the cache survives server restarts.
        save_wd_tag_stats_cache(stats)
    except Exception:
        logger.debug("WD-Tagger stats warm-up skipped", exc_info=True)


def _ensure_wt_stats_warmup(wt_importer) -> None:
    global _wt_stats_warmup_started
    with _wt_stats_warmup_lock:
        if _wt_stats_warmup_started:
            return
        _wt_stats_warmup_started = True
    threading.Thread(
        target=_warmup_wt_stats_cache,
        args=(wt_importer,),
        daemon=True,
        name="wt-stats-warmup",
    ).start()


def register_batch_routes(bp, wt_importer, require_admin_scope, _logger):
    global _wt_importer_ref
    _wt_importer_ref = wt_importer
    # Kick off a background warm-up so the first /api/wd-tagger/stats poll
    # finds a populated SWR cache instead of paying the 2.5s aggregate cost.
    _ensure_wt_stats_warmup(wt_importer)

    @bp.route("/api/wd-tagger/batch", methods=["POST"])
    async def api_wt_batch():
        """Legacy batch endpoint — shim over retag_jobs.start_batch.

        file_ids present -> scope=batch; otherwise -> scope=backfill. The
        legacy response and input shape are preserved for existing callers.
        """
        data = await request.get_json(silent=True) or {}
        file_ids = data.get("file_ids")
        try:
            limit = parse_int_field(
                data,
                "limit",
                default=100,
                minimum=0,
                maximum=500,
            )
            force = parse_bool_field(data, "force", False)
        except ValueError as exc:
            return api_error(str(exc), 400, code="invalid_value")
        scan_root = data.get("scan_root", "")

        if file_ids is not None and not isinstance(file_ids, list):
            return api_error("file_ids must be a list", 400, code="invalid_input")
        if isinstance(file_ids, list) and len(file_ids) > 500:
            return api_error("file_ids max 500", 400, code="batch_too_large")

        from core.configuration.api import load_config_json

        cfg = (load_config_json(None) or {}).get("wd_tagger", {})
        model_id = (
            cfg.get("inference_default_model")
            or cfg.get("model")
            or "SmilingWolf/wd-swinv2-tagger-v3"
        )
        thresholds = {
            "general": float(cfg.get("general_threshold", 0.35)),
            "character": float(cfg.get("character_threshold", 0.85)),
        }

        from extensions.builtin_wd_tagger.core_impl.retag_jobs import start_batch

        kwargs: dict = {
            "model_id": model_id,
            "thresholds": thresholds,
            "limit": limit,
        }
        if file_ids is not None:
            kwargs["scope"] = "batch"
            kwargs["file_ids"] = list(file_ids)
        else:
            kwargs["scope"] = "backfill"
            kwargs["scan_root"] = scan_root
            kwargs["force"] = force

        result = await run_db_sync(start_batch, **kwargs)
        if "error" in result:
            return api_error(
                result["error"],
                409,
                code=result.get("code", "batch_error"),
            )
        return api_result(result)

    @bp.route("/api/wd-tagger/batch/cancel", methods=["POST"])
    async def api_wt_batch_cancel():
        from core.jobs_core.jobs import job_manager

        if job_manager.cancel_job("wd_tagger"):
            return api_result(
                {
                    "status": "cancelling",
                    "message": "Batch tagging cancel requested",
                }
            )
        return api_error("No running batch tagging job", 404, code="job_not_running")

    @bp.route("/api/wd-tagger/stats", methods=["GET"])
    async def api_wt_stats():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        # 1. In-memory SWR cache (sub-ms)
        cached = _WT_STATS_CACHE.peek("payload")
        if cached is not None:
            return api_result(cached)

        # 2. DB-backed persistent cache (O(1), survives restarts)
        store_mod = wt_importer("store")
        db_cached = store_mod.load_wd_tag_stats_cache()
        if db_cached is not None:
            _WT_STATS_CACHE.put("payload", db_cached)
            # Kick a background refresh so the next request is fresh.
            _ensure_wt_stats_warmup(wt_importer)
            return api_result(db_cached)

        # 3. Cold path: recompute synchronously (only on very first run ever).
        def _fetch_stats():
            get_wd_tag_stats = store_mod.get_wd_tag_stats
            count_untagged_unknown_files = store_mod.count_untagged_unknown_files
            stats = get_wd_tag_stats()
            stats["untagged_unknown"] = count_untagged_unknown_files()
            return stats

        result = await run_db_sync(_fetch_stats)
        _WT_STATS_CACHE.put("payload", result)
        return api_result(result)

    @bp.route("/api/wd-tagger/untagged", methods=["GET"])
    async def api_wt_untagged():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        limit = request.args.get("limit", "100")
        offset = request.args.get("offset", "0")
        try:
            limit_int = max(1, min(int(limit), 500))
        except (ValueError, TypeError):
            limit_int = 100
        try:
            offset_int = max(0, int(offset))
        except (ValueError, TypeError):
            offset_int = 0

        def _fetch(limit_value, offset_value):
            store_mod = wt_importer("store")
            get_untagged_unknown_files = store_mod.get_untagged_unknown_files
            count_untagged_unknown_files = store_mod.count_untagged_unknown_files
            files = get_untagged_unknown_files(
                limit=limit_value,
                offset=offset_value,
            )
            total = count_untagged_unknown_files()
            return {"files": files, "total": total}

        return api_result(await run_db_sync(_fetch, limit_int, offset_int))
