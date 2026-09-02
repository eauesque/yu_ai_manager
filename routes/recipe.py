"""Recipe share API routes.

Thin layer: auth -> heavy_io -> Response.
Domain logic lives in core/recipe_api/.
"""
from __future__ import annotations

import json

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.thread_pool import run_in_heavy_io
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

bp = Blueprint("recipe", __name__)

_MAX_BATCH = 100
_MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MB
_MAX_EXPORT_BATCH = 500  # hard cap for bulk recipe export


@bp.route("/api/recipe/export/<int:file_id>", methods=["GET"])
async def api_recipe_export(file_id: int):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    from core.recipe_api import build_recipe
    from core.services_core.db_api import get_readonly_db

    def _build():
        db = get_readonly_db()
        return build_recipe(file_id, db)

    recipe = await run_in_heavy_io(_build)
    if recipe is None:
        return api_error("no gen metadata for this file", 404)
    return api_result(recipe, 200)


@bp.route("/api/recipe/export/batch", methods=["POST"])
async def api_recipe_export_batch():
    """Bulk recipe export for search-result selections.

    Body: {"file_ids": [int, ...]}  — max 500 IDs.
    Returns: {"data": [recipe, ...], "skipped": int}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    body = await request.get_data()
    if len(body) > _MAX_BODY_BYTES:
        return api_error("payload too large", 413)

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return api_error("invalid JSON", 400)

    if not isinstance(data, dict) or "file_ids" not in data:
        return api_error("expected {\"file_ids\": [...]}", 400)

    file_ids = data["file_ids"]
    if not isinstance(file_ids, list):
        return api_error("file_ids must be an array", 400)
    if len(file_ids) > _MAX_EXPORT_BATCH:
        return api_error(f"too many IDs (max {_MAX_EXPORT_BATCH})", 400)

    # Validate all IDs are integers
    try:
        file_ids = [int(fid) for fid in file_ids]
    except (TypeError, ValueError):
        return api_error("file_ids must be integers", 400)

    from core.recipe_api import build_recipe
    from core.services_core.db_api import get_readonly_db

    def _build_all():
        db = get_readonly_db()
        recipes = []
        skipped = 0
        for fid in file_ids:
            r = build_recipe(fid, db)
            if r is not None:
                recipes.append(r)
            else:
                skipped += 1
        return recipes, skipped

    recipes, skipped = await run_in_heavy_io(_build_all)
    return api_result({"recipes": recipes, "skipped": skipped}, 200)


@bp.route("/api/recipe/import", methods=["POST"])
async def api_recipe_import():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    body = await request.get_data()
    if len(body) > _MAX_BODY_BYTES:
        return api_error("payload too large (max 4 MB)", 413)

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return api_error("invalid JSON", 400)

    if not isinstance(data, dict):
        return api_error("expected a recipe object", 400)

    schema = data.get("schema", "")
    if schema != "yu://recipe/1":
        return api_error(f"unsupported schema: {schema!r}", 422)

    from core.recipe_api import fill_recipe

    try:
        result = await run_in_heavy_io(lambda: fill_recipe(data))
    except ValueError as exc:
        return api_error(str(exc), 422)
    return api_result(result, 200)


@bp.route("/api/recipe/import/batch", methods=["POST"])
async def api_recipe_import_batch():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    body = await request.get_data()
    if len(body) > _MAX_BODY_BYTES:
        return api_error("payload too large (max 4 MB)", 413)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return api_error("invalid JSON", 400)

    if not isinstance(data, list):
        return api_error("expected a JSON array", 400)
    if len(data) > _MAX_BATCH:
        return api_error(f"too many recipes (max {_MAX_BATCH})", 400)

    from core.recipe_api import fill_recipe

    def _fill_all():
        results = []
        for item in data:
            if not isinstance(item, dict) or item.get("schema") != "yu://recipe/1":
                results.append(
                    {
                        "bridge_id": item.get("bridge_id") if isinstance(item, dict) else None,
                        "generate_url": None,
                        "generate_body": None,
                        "import_warnings": ["invalid_schema"],
                    }
                )
            else:
                try:
                    results.append(fill_recipe(item))
                except ValueError as exc:
                    results.append({
                        "bridge_id": item.get("bridge_id"),
                        "generate_url": None,
                        "generate_body": None,
                        "import_warnings": [f"invalid_recipe: {exc}"],
                    })
        return results

    results = await run_in_heavy_io(_fill_all)
    return api_result(results, 200)
