"""Quart blueprint factory for the Favorites Manager extension."""

from quart import Blueprint, Response, jsonify, render_template, request

from core.collection_api.favorites_response import (
    invalidate_favorites_check_cache,
)
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from . import (
    batch_add_favorites,
    batch_remove_favorites,
    get_favorite_file_paths,
)
from .favorites_export import (
    build_export_zip_filename,
    export_favorites_folder,
    open_favorites_zip_stream,
)


def create_favorites_manager_blueprint(import_name: str):
    bp = Blueprint(
        "ext_favorites_manager",
        import_name,
        template_folder="templates",
    )


    @bp.route("/")
    async def manager_ui():
        return await render_template("favorites_manager.html")

    # ------------------------------------------------------------------
    # Batch APIs
    # ------------------------------------------------------------------

    @bp.route("/api/batch-add", methods=["POST"])
    async def api_batch_add():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        file_ids = data.get("file_ids", [])
        if not file_ids or not isinstance(file_ids, list):
            return jsonify({"ok": False, "error": "file_ids list required"}), 400

        collection_id = data.get("collection_id", 1)
        if not isinstance(collection_id, int) or collection_id < 1:
            collection_id = 1

        result = batch_add_favorites(file_ids, collection_id)
        invalidate_favorites_check_cache()
        return jsonify({"ok": True, **result})

    @bp.route("/api/batch-remove", methods=["POST"])
    async def api_batch_remove():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        file_ids = data.get("file_ids", [])
        if not file_ids or not isinstance(file_ids, list):
            return jsonify({"ok": False, "error": "file_ids list required"}), 400

        collection_id = data.get("collection_id")
        if collection_id is not None and (not isinstance(collection_id, int) or collection_id < 1):
            collection_id = None

        result = batch_remove_favorites(file_ids, collection_id)
        invalidate_favorites_check_cache()
        return jsonify({"ok": True, **result})

    # ------------------------------------------------------------------
    # Manager data API
    # ------------------------------------------------------------------

    @bp.route("/api/images")
    async def api_manager_images():
        """Return image list for manager grid with thumbnail URLs."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        collection_id_str = request.args.get("collection_id", "")
        cid = int(collection_id_str) if collection_id_str else None

        file_paths = get_favorite_file_paths(collection_id=cid)
        images = []
        for fid, path in file_paths:
            images.append({"id": fid, "path": path})
        return jsonify({"ok": True, "images": images, "total": len(images)})

    # ------------------------------------------------------------------
    # ZIP streaming export
    # ------------------------------------------------------------------

    @bp.route("/api/export/zip")
    async def api_export_zip():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        collection_id_str = request.args.get("collection_id", "")
        cid = int(collection_id_str) if collection_id_str else None

        zip_file = open_favorites_zip_stream(cid)
        if zip_file is None:
            return jsonify({"ok": False, "error": "No files to export"}), 404

        zip_filename = build_export_zip_filename(cid)

        def generate():
            try:
                while True:
                    chunk = zip_file.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                zip_file.close()

        headers = {
            "Content-Type": "application/zip",
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
        }
        return Response(generate(), headers=headers)

    # ------------------------------------------------------------------
    # Symlink folder export
    # ------------------------------------------------------------------

    @bp.route("/api/export/folder", methods=["POST"])
    async def api_export_folder():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        dest_path = data.get("dest_path", "")

        collection_id = data.get("collection_id")
        if collection_id is not None and (not isinstance(collection_id, int) or collection_id < 1):
            collection_id = None

        result = export_favorites_folder(dest_path, collection_id)
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    return bp
