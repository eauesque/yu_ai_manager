"""Search and caption routes for Hailo semantic search."""

import datetime
import logging

from quart import jsonify, request

from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from .hailo_semantic_search_common import ext_config


def _build_filter_ids(con, args) -> "set | None":
    conditions: list[str] = []
    params: list = []
    fmt = args.get("format", "all")
    if fmt and fmt != "all":
        if fmt == "image":
            conditions.append("lower(path) REGEXP ?")
            params.append(r"\.(png|jpg|jpeg|webp|gif|avif|bmp|tiff|tif|heif|heic|jxl|svg)$")
        elif fmt == "video":
            conditions.append("lower(path) REGEXP ?")
            params.append(r"\.(webm|mp4|avi|mov|mkv|m4v|ogv)$")
        exts = args.get("format_exts", "")
        if exts:
            import re as _re
            ext_list = [
                _re.escape(ext.strip().lstrip(".").lower())
                for ext in exts.split(",")
                if ext.strip() and _re.match(r'^[a-z0-9]{1,10}$', ext.strip().lstrip(".").lower())
            ]
            if ext_list:
                conditions.append("lower(path) REGEXP ?")
                params.append(r"\.(" + "|".join(ext_list) + r")$")
    for key, column, adjust in [("from", "mtime >= ?", 0), ("to", "mtime < ?", 86400)]:
        raw = args.get(key, "")
        if raw:
            try:
                # Naive on purpose: the user typed a local date, and
                # `.timestamp()` on a naive value reads local midnight --
                # the boundary they mean. UTC would move the filter edge
                # by the UTC offset.
                ts = (
                    int(
                        datetime.datetime.strptime(  # noqa: DTZ007
                            raw, "%Y-%m-%d"
                        ).timestamp()
                    )
                    + adjust
                )
                conditions.append(column)
                params.append(ts)
            except ValueError:
                pass
    model = args.get("model_filter", "")
    if model and model != "all":
        conditions.append("id IN (SELECT file_id FROM templates WHERE meta_source = ?)")
        params.append(model)
    for field, op in [("min_width", ">="), ("max_width", "<="), ("min_height", ">="), ("max_height", "<=")]:
        raw = args.get(field, "")
        if raw:
            try:
                value = int(raw)
                if value > 0:
                    conditions.append(f"{'width' if 'width' in field else 'height'} {op} ?")
                    params.append(value)
            except ValueError:
                pass
    in_path = args.get("in_path", "")
    if in_path:
        conditions.append("path LIKE ?")
        params.append(f"%{in_path}%")
    if args.get("fav_only") == "true":
        conditions.append("id IN (SELECT file_id FROM favorites)")
    if not conditions:
        return None
    rows = con.execute(
        f"SELECT id FROM files WHERE is_deleted = 0 AND {' AND '.join(conditions)}",
        params,
    )
    return {row[0] for row in rows}


def register_search_routes(bp):
    @bp.route("/api/search")
    async def api_search():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.clip_core.search import semantic_search
        from core.services_core.db_api import get_readonly_db
        from core.services_core.db_async import run_db_sync

        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"status": "error", "message": "Query parameter 'q' is required"}), 400
        if len(query) > 500:
            return jsonify({"status": "error", "message": "Query too long (max 500 chars)"}), 400

        limit = min(int(request.args.get("limit") or 50), 200)
        threshold = float(request.args.get("threshold") or ext_config("similarity_threshold", 0.2))
        filter_args = dict(request.args)

        try:
            def _do_search():
                con = get_readonly_db()
                return semantic_search(query, limit=limit, threshold=threshold, allowed_ids=_build_filter_ids(con, filter_args))

            return jsonify(await run_db_sync(_do_search))
        except ImportError as exc:
            return jsonify({"status": "error", "message": f"Text encoder not available: {exc}"}), 503
        except Exception as exc:
            logging.getLogger(__name__).error("Semantic search failed: %s", exc, exc_info=True)
            return jsonify({"status": "error", "message": f"Search failed: {type(exc).__name__}"}), 500

    @bp.route("/api/caption/start", methods=["POST"])
    async def api_caption_start():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.caption_runner import start_captioning
        data = await request.get_json(silent=True) or {}
        file_ids = [fid for fid in data.get("file_ids", []) if isinstance(fid, int) and fid > 0]
        if not file_ids:
            return jsonify({"status": "error", "message": "No valid file_ids"}), 400
        return jsonify(start_captioning(file_ids=file_ids, prompt=data.get("prompt", "Describe this image in detail."), model=data.get("model", "qwen2-vl-2b-instruct")))

    @bp.route("/api/caption/status")
    async def api_caption_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.caption_runner import get_caption_status
        return jsonify(get_caption_status())

    @bp.route("/api/caption/stop", methods=["POST"])
    async def api_caption_stop():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.caption_runner import stop_captioning
        return jsonify(stop_captioning())
