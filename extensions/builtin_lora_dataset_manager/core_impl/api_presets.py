"""Tag preset CRUD API handlers."""

from __future__ import annotations

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from . import store


def register(bp: Blueprint) -> None:
    """Register preset routes on the blueprint."""

    @bp.route("/tag-presets", methods=["GET"])
    async def list_presets():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        presets = store.list_presets()
        return api_result({"presets": presets, "total": len(presets)}, 200)

    @bp.route("/tag-presets", methods=["POST"])
    async def create_preset():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return api_error("name is required", 400)
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            return api_error("tags must be an array", 400)
        try:
            preset = store.create_preset(name, tags)
        except Exception as exc:
            if "UNIQUE" in str(exc):
                return api_error(f"Preset '{name}' already exists", 409)
            raise
        return api_result(preset, 201)

    @bp.route("/tag-presets/<int:preset_id>", methods=["PUT"])
    async def update_preset(preset_id: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        preset = store.update_preset(
            preset_id,
            name=data.get("name"),
            tags=data.get("tags"),
        )
        if not preset:
            return api_error("Preset not found", 404)
        return api_result(preset, 200)

    @bp.route("/tag-presets/<int:preset_id>", methods=["DELETE"])
    async def delete_preset(preset_id: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        if not store.delete_preset(preset_id):
            return api_error("Preset not found", 404)
        return api_result({"deleted": True}, 200)
