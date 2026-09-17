"""Bulk and import/export routes for Prompt Library API."""

from __future__ import annotations

from collections.abc import Callable

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

from .prompt_library_bulk import bulk_delete, bulk_move, bulk_tag, export_library, import_library


def register_bulk_routes(bp: Blueprint, require_admin_scope: Callable[[], object | None] | None = None) -> None:
    @bp.route("/api/prompts/bulk-delete", methods=["POST"])
    async def api_bulk_delete():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        ids = data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return api_error("ids list is required", 400)
        return api_success({"deleted": bulk_delete(ids)})

    @bp.route("/api/prompts/bulk-move", methods=["POST"])
    async def api_bulk_move():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        ids = data.get("ids", [])
        folder_id = data.get("folder_id")
        if not ids or not isinstance(ids, list):
            return api_error("ids list is required", 400)
        if not folder_id:
            return api_error("folder_id is required", 400)
        return api_success({"moved": bulk_move(ids, folder_id)})

    @bp.route("/api/prompts/bulk-tag", methods=["POST"])
    async def api_bulk_tag():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        ids = data.get("ids", [])
        tag_ids = data.get("tag_ids", [])
        if not ids or not isinstance(ids, list):
            return api_error("ids list is required", 400)
        if not tag_ids or not isinstance(tag_ids, list):
            return api_error("tag_ids list is required", 400)
        return api_success({"tagged": bulk_tag(ids, tag_ids)})

    @bp.route("/api/export", methods=["GET"])
    async def api_export():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        return api_success(export_library(request.args.get("folder_id", type=int)))

    @bp.route("/api/import", methods=["POST"])
    async def api_import():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        if "prompts" not in data:
            return api_error("Invalid import format: 'prompts' key missing", 400)
        return api_success(import_library(data))
