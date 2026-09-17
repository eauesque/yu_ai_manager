"""Stats API routes."""

from quart import Blueprint, request

from core.infra_core.api_errors import api_result
from core.infra_core.api_params import get_str_arg
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.services_core.db_api import get_readonly_db
from core.services_core.db_async import run_db_sync
from core.stats_api.stats_cache import get_cached_stats_all, get_cached_story

bp = Blueprint("stats", __name__)

# Short response cache for /api/stats. The inner stats_cache covers the heavy
# DB work, but the route still pays for executor dispatch + dict build on
# every poll. 5s TTL coalesces near-simultaneous polls without holding stale
# data when the underlying cache invalidates.
_BASIC_STATS_CACHE = SimpleTTLCache(ttl_seconds=5.0, max_entries=2)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _with_db(builder):
    con = get_readonly_db()
    return builder(con)


@bp.route("/api/stats/all")
async def api_stats_all():
    """Return all stats results in one response (cached)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(_with_db, get_cached_stats_all), 200)


@bp.route("/api/stats")
async def api_stats():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    cached = _BASIC_STATS_CACHE.peek("basic")
    if cached is not None:
        return api_result(cached, 200)
    all_stats = await run_db_sync(_with_db, get_cached_stats_all)
    result = dict(all_stats.get("basic") or {})
    if all_stats.get("_stale"):
        result["_stale"] = True
    else:
        # Only cache fully-resolved snapshots; stale results would otherwise
        # pin the "_stale" flag for the entire TTL window.
        _BASIC_STATS_CACHE.put("basic", result)
    return api_result(result, 200)


@bp.route("/api/stats/timeline")
async def api_stats_timeline():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    granularity = get_str_arg(request.args, ("granularity", "g", "interval"), "month")
    if granularity == "month":
        return api_result(
            await run_db_sync(_with_db, lambda con: get_cached_stats_all(con)["timeline"]), 200
        )
    # Non-month granularity: compute directly (not cached)
    from core.stats_api.timeline import build_timeline_stats
    return api_result(
        await run_db_sync(_with_db, lambda con: build_timeline_stats(con, granularity)), 200
    )


@bp.route("/api/stats/hourly")
async def api_stats_hourly():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(_with_db, lambda con: get_cached_stats_all(con)["hourly"]), 200)


@bp.route("/api/stats/models")
async def api_stats_models():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(_with_db, lambda con: get_cached_stats_all(con)["models"]), 200)


@bp.route("/api/stats/resolutions")
async def api_stats_resolutions():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(
        await run_db_sync(_with_db, lambda con: get_cached_stats_all(con)["resolutions"]), 200
    )


@bp.route("/api/stats/story")
async def api_stats_story():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(_with_db, get_cached_story), 200)
