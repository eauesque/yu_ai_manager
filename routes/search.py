"""Search API routes."""

import asyncio

from quart import Blueprint, current_app, request, session

from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.infra_core.inflight_dedupe import dedupe_awaitable
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.search_api.search_grouped import (
    build_grouped_search_response,
    build_grouped_search_warm_response,
    warm_response_cache_peek,
)
from core.search_api.search_response import build_search_count_response, build_search_response
from core.search_api.search_union import build_union_search_response
from core.search_api.server_info import build_server_info_response
from core.search_api.suggest_embedding_response import build_suggest_embedding_response
from core.search_api.suggest_lora_response import build_suggest_lora_response
from core.search_api.suggest_response import build_suggest_response
from core.services_core.db_async import run_db_sync
from core.services_core.market_quotes import (
    get_market_quotes_payload,
    market_quotes_fallback_payload,
)
from core.web.api_rate_limit import get_client_ip
from core.web.auth_restart import is_local_request
from core.web.public_host import resolve_public_host

bp = Blueprint("search", __name__)


async def _dedupe_db_get(name: str, args: dict, fn):
    """Share identical concurrent GET work before it reaches the DB executor."""
    return await dedupe_awaitable(name, args, lambda: run_db_sync(fn, dict(args)))


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/search")
async def api_search():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    payload, status = await run_db_sync(build_search_response, args)
    return api_result(payload, status)


@bp.route("/api/search-count")
async def api_search_count():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    payload, status = await _dedupe_db_get("search-count", args, build_search_count_response)
    return api_result(payload, status)


@bp.route("/api/search-grouped")
async def api_search_grouped():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    payload, status = await run_db_sync(build_grouped_search_response, args)
    return api_result(payload, status)


@bp.route("/api/search-grouped/warm")
async def api_search_grouped_warm():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    # Fast path: skip the DB executor entirely if a recent warm for the same
    # search params is still cached. Warm is fire-and-forget on the client, so
    # avoiding a DB worker slot here directly reduces contention with /api/search.
    cached = warm_response_cache_peek(args)
    if cached is not None:
        payload, status = cached
        return api_result(payload, status)
    payload, status = await _dedupe_db_get("search-grouped-warm", args, build_grouped_search_warm_response)
    return api_result(payload, status)


# Short TTL response cache for /api/server-info. Inner DB stats already cache
# 180s, but the outer build path (LAN IP enumeration, profile listing, UI
# discovery, config.json read) still costs ~400ms cold and runs on every
# poll. Keyed on the per-request inputs that actually change the payload.
_SERVER_INFO_CACHE = SimpleTTLCache(ttl_seconds=5.0, max_entries=32)


@bp.route("/api/server-info")
async def api_server_info():
    config = current_app.config
    sess = dict(session)
    client_ip = (get_client_ip() or "").strip().lower()
    local_only_ok = is_local_request()
    host = resolve_public_host(client_ip)

    cache_key = (local_only_ok, host, bool(sess.get("pin_ok")))
    cached = _SERVER_INFO_CACHE.peek(cache_key)
    if cached is not None:
        return api_result(cached, 200)

    def _build():
        return build_server_info_response(config, sess, local_only_ok, host)

    payload = await run_db_sync(_build)
    _SERVER_INFO_CACHE.put(cache_key, payload)
    return api_result(payload, 200)


@bp.route("/api/market/quotes")
async def api_market_quotes():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # Outer bound. The fetcher caps its own symbol loop, but `urlopen`'s timeout
    # does not cover `getaddrinfo`, so one lookup on a host with an unreachable
    # resolver can outlast every internal budget. The static rows are the right
    # answer then -- this is a ticker widget, not a trade.
    try:
        payload = await asyncio.wait_for(
            run_db_sync(get_market_quotes_payload), timeout=8.0
        )
    except TimeoutError:
        payload = market_quotes_fallback_payload()
    return api_result(payload, 200)


@bp.route("/api/suggest")
async def api_suggest():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    payload = await _dedupe_db_get("suggest", args, build_suggest_response)
    return api_result(payload, 200)


@bp.route("/api/search-union", methods=["POST"])
async def api_search_union():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    payload, status = await run_db_sync(build_union_search_response, data)
    return api_result(payload, status)


@bp.route("/api/suggest/lora")
async def api_suggest_lora():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    payload = await _dedupe_db_get("suggest-lora", args, build_suggest_lora_response)
    return api_result(payload, 200)


@bp.route("/api/suggest/embedding")
async def api_suggest_embedding():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    args = dict(request.args)
    payload = await _dedupe_db_get("suggest-embedding", args, build_suggest_embedding_response)
    return api_result(payload, 200)
