"""Project CRUD API handlers."""

from __future__ import annotations

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from . import store
from .caption_builder import build_caption, get_tag_summary


def register(bp: Blueprint) -> None:
    """Register project routes on the blueprint."""

    @bp.route("/projects", methods=["GET"])
    async def list_projects():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        projects = store.list_projects()
        return api_result({
            "projects": [_proj_dict(p) for p in projects],
            "total": len(projects),
        }, 200)

    @bp.route("/projects", methods=["POST"])
    async def create_project():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        concept = (data.get("concept") or "").strip()
        if not name:
            return api_error("name is required", 400)
        if not concept:
            return api_error("concept is required", 400)
        base_model = data.get("base_model", "sdxl")
        if base_model not in ("sd15", "sdxl"):
            return api_error("base_model must be 'sd15' or 'sdxl'", 400)
        repeat = int(data.get("repeat", 10))
        if repeat < 1 or repeat > 999:
            return api_error("repeat must be 1-999", 400)
        raw_scope = data.get("model_scope", "active")
        if raw_scope is None:
            model_scope = "active"
        elif isinstance(raw_scope, str):
            model_scope = raw_scope.strip() or "active"
        else:
            return api_error("model_scope must be a string", 400)
        proj = store.create_project(name, concept, base_model, repeat, model_scope)
        return api_result(_proj_dict(proj), 201)

    @bp.route("/projects/<int:pid>", methods=["GET"])
    async def get_project(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        proj = store.get_project(pid)
        if not proj:
            return api_error("Project not found", 404)
        return api_result(_proj_dict(proj), 200)

    @bp.route("/projects/<int:pid>", methods=["PUT"])
    async def update_project(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        proj = store.get_project(pid)
        if not proj:
            return api_error("Project not found", 404)
        data = await request.get_json(silent=True) or {}
        if "model_scope" in data:
            raw_scope = data["model_scope"]
            if raw_scope is None:
                data["model_scope"] = "active"
            elif isinstance(raw_scope, str):
                data["model_scope"] = raw_scope.strip() or "active"
            else:
                return api_error("model_scope must be a string", 400)
        updated = store.update_project(pid, **data)
        return api_result(_proj_dict(updated), 200)

    @bp.route("/projects/<int:pid>", methods=["DELETE"])
    async def delete_project(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        if not store.delete_project(pid):
            return api_error("Project not found", 404)
        return api_result({"deleted": True}, 200)

    @bp.route("/projects/<int:pid>/tags", methods=["GET"])
    async def project_tags(pid: int):
        """Get aggregated tag summary for project files."""
        proj = store.get_project(pid)
        if not proj:
            return api_error("Project not found", 404)
        limit = request.args.get("limit", 200, type=int)
        tags = get_tag_summary(proj.file_ids, limit=limit,
                               model_scope=proj.model_scope)
        return api_result({"tags": tags, "file_count": len(proj.file_ids)}, 200)

    @bp.route("/projects/<int:pid>/caption-preview", methods=["GET"])
    async def caption_preview(pid: int):
        """Preview caption for a specific file in the project."""
        proj = store.get_project(pid)
        if not proj:
            return api_error("Project not found", 404)
        file_id = request.args.get("file_id", type=int)
        if file_id is None:
            # Use first file
            if not proj.file_ids:
                return api_error("No files in project", 400)
            file_id = proj.file_ids[0]
        caption = build_caption(
            file_id,
            proj.tag_exclude,
            proj.base_model,
            model_scope=proj.model_scope,
        )
        return api_result({"file_id": file_id, "caption": caption}, 200)


def _proj_dict(proj) -> dict:
    """Convert LoraProject to API response dict."""
    if proj is None:
        return {}
    return {
        "id": proj.id,
        "name": proj.name,
        "concept": proj.concept,
        "repeat": proj.repeat,
        "base_model": proj.base_model,
        "model_scope": proj.model_scope,
        "tag_exclude": proj.tag_exclude,
        "tag_preset": proj.tag_preset,
        "search_query": proj.search_query,
        "file_ids": proj.file_ids,
        "file_count": len(proj.file_ids),
        "created_at": proj.created_at,
        "updated_at": proj.updated_at,
    }
