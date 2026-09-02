"""Output listing and delivery routes for Freeze & Pull-back."""

from __future__ import annotations

import os

from quart import jsonify, send_file

from core.infra_core.api_errors import api_error


def _resolve_output_path(default_output_dir: str, filename: str) -> str:
    filepath = os.path.join(default_output_dir, filename)
    if not os.path.abspath(filepath).startswith(os.path.abspath(default_output_dir)):
        return ""
    return filepath


def register_output_routes(
    bp,
    *,
    default_output_dir: str,
    safe_filename_pattern,
    list_outputs_fn,
    require_admin_scope,
):
    @bp.route("/api/outputs")
    async def api_outputs():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        outputs = list_outputs_fn()
        return jsonify({"outputs": outputs, "total": len(outputs)})

    @bp.route("/api/outputs/<filename>")
    async def api_output_file(filename: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        if not safe_filename_pattern.match(filename):
            return api_error("Invalid filename", 400)

        filepath = _resolve_output_path(default_output_dir, filename)
        if not filepath:
            return api_error("Invalid path", 400)
        if not os.path.isfile(filepath):
            return api_error("File not found", 404)

        ext = os.path.splitext(filepath)[1].lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".gif": "image/gif",
            ".png": "image/png",
            ".webp": "image/webp",
            ".webm": "video/webm",
        }
        mimetype = mime_map.get(ext, "application/octet-stream")
        return await send_file(filepath, mimetype=mimetype)

    @bp.route("/api/outputs/<filename>", methods=["DELETE"])
    async def api_delete_output(filename: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        if not safe_filename_pattern.match(filename):
            return api_error("Invalid filename", 400)

        filepath = _resolve_output_path(default_output_dir, filename)
        if not filepath:
            return api_error("Invalid path", 400)
        if not os.path.isfile(filepath):
            return api_error("File not found", 404)

        os.remove(filepath)
        sidecar_path = os.path.splitext(filepath)[0] + ".json"
        if os.path.isfile(sidecar_path):
            os.remove(sidecar_path)

        return jsonify({"ok": True, "deleted": filename})

    @bp.route("/api/thumbnail/<int:file_id>")
    async def api_thumbnail(file_id: int):
        """Return the thumbnail path and resolution for a file_id."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from core.services_core.db_api import get_readonly_db

        con = get_readonly_db()
        row = con.execute(
            "SELECT path, width, height FROM files WHERE id = ? AND is_deleted = 0",
            (file_id,),
        ).fetchone()
        if not row or not os.path.isfile(row[0]):
            return api_error("Image not found", 404)

        result = {"ok": True, "file_id": file_id, "path": row[0]}
        if row[1] and row[2]:
            result["width"] = row[1]
            result["height"] = row[2]
        return jsonify(result)
