"""Single-file tagging and tag CRUD routes for WD-Tagger."""

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from routes.wd_tagger_route_utils import parse_bool_field


def register_tag_routes(bp, wt_importer, _require_admin_scope, _logger):
    @bp.route("/api/wd-tagger/tag/<int:file_id>", methods=["POST"])
    async def api_wt_tag_one(file_id):
        force = False
        data = await request.get_json(silent=True)
        if isinstance(data, dict):
            try:
                force = parse_bool_field(data, "force", False)
            except ValueError as exc:
                return api_error(str(exc), 400, code="invalid_value")

        tag_one_file = wt_importer("single_ops").tag_one_file
        result = await run_db_sync(tag_one_file, file_id, force=force)
        if "error" in result:
            return api_error(
                result["error"],
                400,
                code=result.get("code", "tag_error"),
            )
        return api_result(result)

    @bp.route("/api/wd-tagger/tags/<int:file_id>", methods=["GET"])
    async def api_wt_tags_get(file_id):
        get_wd_tags = wt_importer("store").get_wd_tags
        include_all = request.args.get("all", "").lower() in ("1", "true", "yes")
        model = None if include_all else request.args.get("model")
        tags = await run_db_sync(
            get_wd_tags,
            file_id,
            model=model,
            include_all=include_all,
        )
        return api_result({"file_id": file_id, "tags": tags})

    @bp.route("/api/wd-tagger/tags/<int:file_id>", methods=["DELETE"])
    async def api_wt_tags_delete(file_id):
        model = request.args.get("model")
        delete_wd_tags = wt_importer("store").delete_wd_tags
        count = await run_db_sync(delete_wd_tags, file_id, model=model)
        return api_result({"file_id": file_id, "deleted": count})

    @bp.route("/api/wd-tagger/tags/batch", methods=["DELETE"])
    async def api_wt_tags_delete_batch():
        data = await request.get_json(silent=True) or {}
        file_ids = data.get("file_ids")
        model = data.get("model")

        if not isinstance(file_ids, list):
            return api_error("file_ids must be a list", 400, code="invalid_input")
        if len(file_ids) > 500:
            return api_error("file_ids max 500", 400, code="batch_too_large")

        delete_wd_tags_batch = wt_importer("store").delete_wd_tags_batch
        result = await run_db_sync(delete_wd_tags_batch, file_ids, model=model)
        return api_result(result)
