"""Tag routes for Prompt Library API."""

from __future__ import annotations

import logging
from collections.abc import Callable

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

from .prompt_library_tags import create_tag, delete_tag, list_tags, set_prompt_tags

logger = logging.getLogger(__name__)


def register_tag_routes(bp: Blueprint, require_admin_scope: Callable[[], object | None] | None = None) -> None:
    @bp.route("/api/tags", methods=["GET"])
    async def api_tags():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        return api_success({"tags": list_tags()})

    @bp.route("/api/tags", methods=["POST"])
    async def api_create_tag():
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        name = (data.get("name") or "").strip()
        if not name:
            return api_error("name is required", 400, code="missing_name")
        try:
            tag = create_tag(name)
        except ValueError:
            logger.exception("Failed to create prompt-library tag")
            return api_error("Tag already exists", 400, code="duplicate_tag")
        return api_success({"tag": tag}, 201)

    @bp.route("/api/tags/<int:tid>", methods=["DELETE"])
    async def api_delete_tag(tid: int):
        if not delete_tag(tid):
            return api_error("Tag not found", 404, code="not_found")
        return api_success({"deleted": tid})

    @bp.route("/api/prompts/<int:pid>/tags", methods=["POST"])
    async def api_set_tags(pid: int):
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        tag_ids = data.get("tag_ids", [])
        if not isinstance(tag_ids, list):
            return api_error("tag_ids must be a list", 400)
        return api_success({"tags": set_prompt_tags(pid, tag_ids)})
