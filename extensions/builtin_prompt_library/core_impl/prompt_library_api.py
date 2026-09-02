"""Quart blueprint factory for the Prompt Library extension.

Folder, tag, bulk, export/import, and from-file routes are split
into prompt_library_api_routes.py.
"""

from __future__ import annotations

from quart import Blueprint, render_template, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from .prompt_library_api_routes import register_extra_routes  # noqa: F401
from .prompt_library_read import get_prompt, list_prompts
from .prompt_library_write import create_prompt, delete_prompt, update_prompt


def create_prompt_library_blueprint(import_name: str) -> Blueprint:
    """Create and return the Prompt Library blueprint."""

    bp = Blueprint(
        "ext_prompt_library",
        import_name,
        template_folder="templates",
    )


    # -- UI page ------------------------------------------------

    @bp.route("/")
    async def library_ui():
        return await render_template("prompt_library.html")

    # -- Info ---------------------------------------------------

    @bp.route("/info")
    async def library_info():
        from quart import jsonify
        return jsonify({"name": "builtin-prompt-library", "version": "1.0.0"})

    # -- GET /api/prompts -- paginated list ----------------------

    @bp.route("/api/prompts", methods=["GET"])
    async def api_list():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        q = request.args.get("q", "").strip() or None
        sort = request.args.get("sort", "updated_at")
        order = request.args.get("order", "desc")
        folder_id = request.args.get("folder_id", type=int)
        tag_id = request.args.get("tag_id", type=int)
        offset = max(0, request.args.get("offset", 0, type=int))
        limit = request.args.get("limit", 50, type=int)
        if limit < 1 or limit > 200:
            limit = 50

        result = list_prompts(
            q=q, sort=sort, order=order,
            folder_id=folder_id, tag_id=tag_id,
            offset=offset, limit=limit,
        )
        return api_success(result)

    # -- GET /api/prompts/<id> -- single prompt ------------------

    @bp.route("/api/prompts/<int:pid>", methods=["GET"])
    async def api_get(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        item = get_prompt(pid)
        if not item:
            return api_error("Prompt not found", 404, code="not_found")
        return api_success({"prompt": item})

    # -- POST /api/prompts -- create -----------------------------

    @bp.route("/api/prompts", methods=["POST"])
    async def api_create():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        title = (data.get("title") or "").strip()
        if not title:
            return api_error("title is required", 400, code="missing_title")

        characters = data.get("characters")
        if isinstance(characters, list):
            characters = [c for c in characters if isinstance(c, dict) and c.get("prompt")]
        else:
            characters = None

        item = create_prompt(
            title=title,
            positive=(data.get("positive") or "").strip(),
            negative=(data.get("negative") or "").strip(),
            seed=str(data.get("seed") or "").strip(),
            steps=str(data.get("steps") or "").strip(),
            sampler=(data.get("sampler") or "").strip(),
            cfg_scale=str(data.get("cfg_scale") or "").strip(),
            model_name=(data.get("model_name") or "").strip(),
            memo=(data.get("memo") or "").strip(),
            source_file_id=data.get("source_file_id"),
            characters=characters,
        )
        return api_success({"prompt": item}, 201)

    # -- PUT /api/prompts/<id> -- update -------------------------

    @bp.route("/api/prompts/<int:pid>", methods=["PUT"])
    async def api_update(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        update_fields = {
            k: data[k] for k in (
                "title", "positive", "negative", "seed", "steps",
                "sampler", "cfg_scale", "model_name", "memo",
            ) if k in data
        }
        if "characters" in data and isinstance(data["characters"], list):
            update_fields["characters"] = [
                c for c in data["characters"]
                if isinstance(c, dict) and c.get("prompt")
            ]
        item = update_prompt(pid, **update_fields)
        if not item:
            return api_error("Prompt not found", 404, code="not_found")
        return api_success({"prompt": item})

    # -- DELETE /api/prompts/<id> -- delete ----------------------

    @bp.route("/api/prompts/<int:pid>", methods=["DELETE"])
    async def api_delete(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        if not delete_prompt(pid):
            return api_error("Prompt not found", 404, code="not_found")
        return api_success({"deleted": pid})

    # -- Register extra route groups (folders, tags, bulk, etc.) --

    register_extra_routes(bp, _require_admin_scope)

    return bp
