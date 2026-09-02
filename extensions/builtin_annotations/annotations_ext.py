"""builtin-annotations Extension entrypoint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import contextlib

from quart import Blueprint, render_template, request  # noqa: E402

from core.infra_core.api_errors import api_error, api_result  # noqa: E402
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from .core_impl import (  # noqa: E402
    delete_annotations_batch,
    get_annotations_for_file,
    get_user_notes,
    search_annotations,
    set_annotations_batch,
)

_BATCH_SET_MAX = 500


def get_blueprint():
    bp = Blueprint("annotations", __name__, template_folder="templates")


    @bp.route("/notes", methods=["GET"])
    async def ui_notes_page():
        return await render_template("annotations/notes.html")

    @bp.route("/notes-data", methods=["GET"])
    async def api_notes_data():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        q = (request.args.get("q", "") or "").strip()
        try:
            limit = min(max(1, int(request.args.get("limit", "50"))), 200)
            offset = max(0, int(request.args.get("offset", "0")))
        except (ValueError, TypeError):
            limit, offset = 50, 0
        results, total = get_user_notes(q=q, limit=limit, offset=offset)
        return api_result(
            {"notes": results, "total": total, "limit": limit, "offset": offset}, 200
        )

    @bp.route("/batch-set", methods=["POST"])
    async def api_annotations_batch_set():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_error("JSON object required", 400, code="invalid_json")

        items = data.get("items")
        if not isinstance(items, list) or len(items) == 0:
            return api_error("items array required", 400, code="batch_empty")
        if len(items) > _BATCH_SET_MAX:
            return api_error(
                f"Batch size {len(items)} exceeds maximum of {_BATCH_SET_MAX}",
                400,
                code="batch_too_large",
            )

        result = set_annotations_batch(items)
        return api_result({"data": result}, 200)

    @bp.route("/<int:file_id>", methods=["GET"])
    async def api_annotations_get(file_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        source = request.args.get("source", "")
        key = request.args.get("key", "")
        annotations = get_annotations_for_file(
            file_id,
            source=source or None,
            key=key or None,
        )
        return api_result({"annotations": annotations}, 200)

    @bp.route("/search", methods=["GET"])
    async def api_annotations_search():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        source = request.args.get("source", "")
        key = request.args.get("key", "")
        min_conf = request.args.get("min_confidence", "")
        max_conf = request.args.get("max_confidence", "")
        limit = request.args.get("limit", "100")
        offset = request.args.get("offset", "0")

        try:
            limit_int = max(1, min(int(limit), 2000))
        except (ValueError, TypeError):
            limit_int = 100
        try:
            offset_int = max(0, int(offset))
        except (ValueError, TypeError):
            offset_int = 0

        min_confidence = None
        if min_conf:
            with contextlib.suppress(ValueError, TypeError):
                min_confidence = float(min_conf)
        max_confidence = None
        if max_conf:
            with contextlib.suppress(ValueError, TypeError):
                max_confidence = float(max_conf)

        result = search_annotations(
            source=source or None,
            key=key or None,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            limit=limit_int,
            offset=offset_int,
        )
        return api_result(result, 200)

    @bp.route("/batch-delete", methods=["POST"])
    async def api_annotations_batch_delete():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_error("JSON object required", 400, code="invalid_json")

        source = data.get("source")
        if not isinstance(source, str) or not source.strip():
            return api_error("source is required", 400, code="invalid_value")

        file_ids = data.get("file_ids")
        if not isinstance(file_ids, list) or len(file_ids) == 0:
            return api_error("file_ids is required (non-empty list)", 400, code="invalid_value")
        if len(file_ids) > 500:
            return api_error("file_ids too large (max 500)", 400, code="batch_too_large")
        key = data.get("key")

        result = delete_annotations_batch(
            source=source.strip(),
            file_ids=file_ids,
            key=key if isinstance(key, str) and key.strip() else None,
        )
        return api_result({"data": result}, 200)

    return bp


__all__ = ["get_blueprint"]
