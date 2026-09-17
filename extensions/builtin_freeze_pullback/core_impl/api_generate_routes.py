"""Generation and job-control routes for Freeze & Pull-back."""

import os

from quart import jsonify, request

from core.infra_core.api_errors import api_error

from .api_db_helpers import resolve_image_path
from .api_params import apply_source_resolution, build_params
from .validation import validate_params


def register_generate_routes(
    bp,
    *,
    check_ffmpeg_fn,
    start_render_job_fn,
    get_job_status_fn,
    cancel_job_fn,
    require_admin_scope,
):
    @bp.route("/api/check")
    async def api_check():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        available = check_ffmpeg_fn()
        return jsonify({"ffmpeg_available": available})

    @bp.route("/api/generate", methods=["POST"])
    async def api_generate():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        body = await request.get_json(silent=True) or {}

        try:
            params = build_params(body)
        except ValueError as exc:
            return api_error(str(exc), 400)

        if params.file_id > 0:
            # Always resolve image path from DB when file_id is provided;
            # ignore any client-supplied image_path to prevent path traversal.
            params.image_path = ""
            path = resolve_image_path(params.file_id)
            if not path:
                return api_error("Image not found for file_id", 404)
            params.image_path = path
        elif params.image_path:
            # Direct path mode: ensure the file actually exists.
            if not os.path.isfile(params.image_path):
                return api_error("Image file not found", 404)

        if params.out_width == 0 or params.out_height == 0:
            apply_source_resolution(params)

        errors = validate_params(params)
        if errors:
            return api_error("; ".join(errors), 400)
        if not check_ffmpeg_fn():
            return api_error("ffmpeg is not available", 503)

        result = start_render_job_fn(params)
        if "error" in result:
            return api_error(result["error"], 409)
        return jsonify({"ok": True, **result})

    @bp.route("/api/status")
    async def api_status():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        return jsonify(get_job_status_fn())

    @bp.route("/api/cancel", methods=["POST"])
    async def api_cancel():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        ok = cancel_job_fn()
        if ok:
            return jsonify({"ok": True, "message": "Cancel requested"})
        return api_error("No active job to cancel", 404)
