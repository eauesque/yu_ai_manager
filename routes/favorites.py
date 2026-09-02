"""Favorites API routes.

Thin layer. Validation, domain calls, and caching live under
``core/collection_api/`` (favorites share the same table as collections).
"""

from quart import Blueprint, request

from core.collection_api import (
    build_check_collections_response,
    build_check_response,
    build_favorites_list_response,
    build_toggle_response,
    parse_check_args,
    parse_check_collections_args,
)
from core.infra_core.api_errors import api_result
from core.infra_core.api_params import clamp_sqlite_int
from core.infra_core.inflight_dedupe import dedupe_db_get
from core.services_core.db_async import run_db_sync

bp = Blueprint("favorites", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/favorites/toggle", methods=["POST"])
async def api_favorites_toggle():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True)
    payload, status = await run_db_sync(build_toggle_response, data)
    return api_result(payload, status)


@bp.route("/api/favorites/check")
async def api_favorites_check():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    ids, cid, err = parse_check_args(
        request.args.get("ids", ""),
        request.args.get("collection_id", ""),
    )
    if err is not None:
        return api_result(err, 400)
    if ids is None:
        return api_result({"favorites": []}, 200)

    # Hot path: every grid render fans this out for visible thumbnails. Dedupe
    # collapses concurrent identical lookups before they hit the DB executor.
    payload = await dedupe_db_get(
        "favorites-check", (sorted(ids), cid), build_check_response, ids, cid
    )
    return api_result(payload, 200)


@bp.route("/api/favorites/check_collections")
async def api_favorites_check_collections():
    """Return which collections a file belongs to."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    file_id, err = parse_check_collections_args(request.args.get("file_id", ""))
    if err is not None:
        return api_result(err, 400)
    if file_id is None:
        return api_result({"collections": []}, 200)

    payload = await dedupe_db_get(
        "favorites-check-collections", file_id, build_check_collections_response, file_id
    )
    return api_result(payload, 200)


@bp.route("/api/favorites/list")
async def api_favorites_list():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    collection_id_str = request.args.get("collection_id", "")
    cid = clamp_sqlite_int(int(collection_id_str)) if collection_id_str else None

    payload = await dedupe_db_get(
        "favorites-list", cid, build_favorites_list_response, cid
    )
    return api_result(payload, 200)
