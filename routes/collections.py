"""Collections API routes.

Thin layer: handles auth, async dispatch (db_sync vs heavy_io), and Response
construction. Validation, domain calls, and caching live under
``core/collection_api/``.
"""

import logging
import time

from quart import Blueprint, Response, request

from core.collection_api import (
    build_collection_csv,
    build_create_response,
    build_delete_response,
    build_list_response,
    build_reorder_response,
    build_update_response,
    run_batch_add,
    run_batch_remove,
    validate_batch_payload,
)
from core.infra_core.api_errors import api_error, api_result
from core.infra_core.thread_pool import run_in_heavy_io
from core.services_core.db_async import run_db_sync

bp = Blueprint("collections", __name__)
logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/collections", methods=["GET"])
async def api_collections_list():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload = await run_db_sync(build_list_response)
    return api_result(payload, 200)


@bp.route("/api/collections", methods=["POST"])
async def api_collections_create():
    data = await request.get_json(silent=True)
    payload, status = await run_db_sync(build_create_response, data)
    return api_result(payload, status)


@bp.route("/api/collections/<int:collection_id>", methods=["PUT"])
async def api_collections_update(collection_id):
    data = await request.get_json(silent=True)
    payload, status = await run_db_sync(build_update_response, collection_id, data)
    return api_result(payload, status)


@bp.route("/api/collections/<int:collection_id>", methods=["DELETE"])
async def api_collections_delete(collection_id):
    try:
        payload, status = await run_db_sync(build_delete_response, collection_id)
    except Exception:
        logger.exception("Failed to delete collection", extra={"collection_id": collection_id})
        return api_result({"error": "Collection could not be deleted"}, 400)
    return api_result(payload, status)


@bp.route("/api/collections/reorder", methods=["POST"])
async def api_collections_reorder():
    data = await request.get_json(silent=True)
    payload, status = await run_db_sync(build_reorder_response, data)
    return api_result(payload, status)


@bp.route("/api/collections/<int:collection_id>/batch-add", methods=["POST"])
async def api_collections_batch_add(collection_id):
    data = await request.get_json(silent=True)
    file_ids, err = validate_batch_payload(data)
    if err is not None:
        body, status, code = err
        return api_error(body["error"], status, code=code)
    # Heavy-io pool: large batches do many writes + cache_invalidate fan-out
    # that we don't want occupying DB executor slots used by /api/search.
    result = await run_in_heavy_io(run_batch_add, file_ids, collection_id)
    return api_result({"data": result}, 200)


@bp.route("/api/collections/<int:collection_id>/batch-remove", methods=["POST"])
async def api_collections_batch_remove(collection_id):
    data = await request.get_json(silent=True)
    file_ids, err = validate_batch_payload(data)
    if err is not None:
        body, status, code = err
        return api_error(body["error"], status, code=code)
    result = await run_in_heavy_io(run_batch_remove, file_ids, collection_id)
    return api_result({"data": result}, 200)


@bp.route("/api/collections/<int:collection_id>/export/csv", methods=["GET"])
async def api_collections_export_csv(collection_id):
    """Export collection files as CSV."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    # CSV build does N+1-ish SQL plus per-row UTF-8 encoding and string I/O —
    # belongs on heavy-io pool, not the DB executor.
    cname, csv_bytes = await run_in_heavy_io(build_collection_csv, collection_id)
    if cname is None:
        return api_result({"error": "collection not found"}, 404)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in cname)
    date_str = time.strftime("%Y-%m-%d")
    filename = f"{safe_name}_{date_str}.csv"

    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/api/collections/<int:collection_id>/export", methods=["GET"])
async def api_collections_export_format(collection_id):
    """Export collection with format query param: recipe_csv | recipe_json."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    import time as _time

    fmt = request.args.get("format", "")
    if fmt not in ("recipe_csv", "recipe_json"):
        return api_error(f"unsupported format: {fmt!r}. Use recipe_csv or recipe_json", 400)

    from core.collection_api.csv_export import (
        build_collection_recipe_csv,
        build_collection_recipe_json,
    )

    if fmt == "recipe_csv":
        cname, csv_bytes = await run_in_heavy_io(build_collection_recipe_csv, collection_id)
        if cname is None:
            return api_error("collection not found", 404)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in cname)
        filename = f"{safe_name}_{_time.strftime('%Y-%m-%d')}_recipe.csv"
        return Response(
            csv_bytes,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    cname, recipes = await run_in_heavy_io(build_collection_recipe_json, collection_id)
    if cname is None:
        return api_error("collection not found", 404)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in cname)
    filename = f"{safe_name}_{_time.strftime('%Y-%m-%d')}_recipe.json"
    import json as _json

    return Response(
        _json.dumps(recipes, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
