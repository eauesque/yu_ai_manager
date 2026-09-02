"""Folder routes for Prompt Library API."""

from __future__ import annotations

from collections.abc import Callable

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

from .prompt_library_folders import (
    assign_prompt_to_folder,
    build_folder_tree,
    create_folder,
    delete_folder,
    list_folders,
    remove_prompt_from_folder,
    update_folder,
)


def register_folder_routes(bp: Blueprint, require_admin_scope: Callable[[], object | None] | None = None) -> None:
    @bp.route("/api/folders", methods=["GET"])
    async def api_folders():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        folders = list_folders()
        return api_success({"folders": folders, "tree": build_folder_tree(folders)})

    @bp.route("/api/folders", methods=["POST"])
    async def api_create_folder():
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        name = (data.get("name") or "").strip()
        if not name:
            return api_error("name is required", 400, code="missing_name")
        return api_success({"folder": create_folder(name, data.get("parent_id"))}, 201)

    @bp.route("/api/folders/<int:fid>", methods=["PUT"])
    async def api_update_folder(fid: int):
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        kwargs = {}
        if "name" in data:
            kwargs["name"] = (data["name"] or "").strip()
        if "parent_id" in data:
            kwargs["parent_id"] = data["parent_id"]
        folder = update_folder(fid, **kwargs)
        if not folder:
            return api_error("Folder not found", 404, code="not_found")
        return api_success({"folder": folder})

    @bp.route("/api/folders/<int:fid>", methods=["DELETE"])
    async def api_delete_folder(fid: int):
        if not delete_folder(fid):
            return api_error("Folder not found", 404, code="not_found")
        return api_success({"deleted": fid})

    @bp.route("/api/prompts/<int:pid>/folder", methods=["POST"])
    async def api_assign_folder(pid: int):
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        folder_id = data.get("folder_id")
        if not folder_id:
            return api_error("folder_id is required", 400)
        assign_prompt_to_folder(pid, folder_id)
        return api_success()

    @bp.route("/api/prompts/<int:pid>/folder", methods=["DELETE"])
    async def api_remove_folder(pid: int):
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        folder_id = data.get("folder_id")
        if not folder_id:
            return api_error("folder_id is required", 400)
        remove_prompt_from_folder(pid, folder_id)
        return api_success()
