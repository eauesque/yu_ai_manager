"""builtin-tag-dictionary Extension entrypoint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import contextlib

from quart import Blueprint, jsonify, request  # noqa: E402

from core.infra_core.api_errors import api_error, api_result  # noqa: E402
from core.infra_core.upload_limits import copy_upload_to_temp  # noqa: E402
from core.web.auth_helpers import require_admin_scope as _require_admin_scope  # noqa: E402

from .core_impl import (  # noqa: E402
    clear_all,
    fuzzy_filter,
    get_stats,
    get_tag_info,
    search_tags,
    suggest_splits,
)
from .core_impl.csv_import import import_csv  # noqa: E402
from .core_impl.tag_splitter import invalidate_cache  # noqa: E402

_MAX_CSV_UPLOAD_BYTES = 16 * 1024 * 1024


def get_blueprint():
    bp = Blueprint("tag_dict", __name__)

    @bp.route("/search")
    async def api_search():
        """Search the tag dictionary."""
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"results": []})

        limit = min(int(request.args.get("limit", "20")), 100)
        use_fuzzy = request.args.get("fuzzy", "").lower() in ("1", "true")

        results = search_tags(q, limit=limit)

        if use_fuzzy and len(results) < limit:
            from .core_impl.store import fuzzy_search_tags
            fuzzy_results = fuzzy_search_tags(q, limit=100)
            fuzzy_filtered = fuzzy_filter(q, fuzzy_results, threshold=2)
            seen = {r["tag_name"].lower() for r in results}
            for fr in fuzzy_filtered:
                if fr["tag_name"].lower() not in seen:
                    fr["match_type"] = "fuzzy"
                    results.append(fr)
                    seen.add(fr["tag_name"].lower())
                    if len(results) >= limit:
                        break

        return jsonify({"results": results})

    @bp.route("/info")
    async def api_info():
        """Return details for a single tag."""
        tag = request.args.get("tag", "").strip()
        if not tag:
            return api_error("tag parameter required", 400)
        info = get_tag_info(tag)
        if info is None:
            return api_error("Tag not found", 404)
        return jsonify(info)

    @bp.route("/stats")
    async def api_stats():
        """Return dictionary statistics."""
        return jsonify(get_stats())

    @bp.route("/import", methods=["POST"])
    async def api_import():
        """Upload and import a CSV file."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        f = (await request.files).get("file")
        if not f:
            return api_error("file required (multipart form)", 400)
        tmp_path = None
        try:
            tmp_path = copy_upload_to_temp(
                f,
                max_bytes=_MAX_CSV_UPLOAD_BYTES,
                suffix=".csv",
                prefix="yu_tag_dict_",
            )
            result = import_csv(tmp_path)
            invalidate_cache()
            return jsonify(result)
        except ValueError as exc:
            return api_error(str(exc), 413)
        finally:
            if tmp_path:
                with contextlib.suppress(OSError):
                    Path(tmp_path).unlink(missing_ok=True)

    @bp.route("/clear", methods=["DELETE"])
    async def api_clear():
        """Delete all entries from the dictionary."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        count = clear_all()
        invalidate_cache()
        return api_result({"deleted": count})

    @bp.route("/split", methods=["POST"])
    async def api_split():
        """Return split candidates for comma-less tags."""
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_error("JSON object required", 400)
        text = (data.get("text") or "").strip()
        if not text:
            return api_error("text required", 400)
        suggestions = suggest_splits(text, max_suggestions=5)
        return jsonify({"suggestions": suggestions})

    return bp


__all__ = ["get_blueprint"]
