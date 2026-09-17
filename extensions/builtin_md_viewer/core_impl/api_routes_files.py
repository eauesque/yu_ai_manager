from quart import jsonify, request

from core.services_core.db_state import get_readonly_db
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from . import store


def register_file_routes(bp, int_param):
    @bp.route("/api/files")
    async def api_files():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()
        query = request.args.get("query", "").strip()
        path_filter = request.args.get("path_filter", "").strip()
        lang_filter = request.args.get("lang", "").strip()
        sort = request.args.get("sort", "mtime")
        order = request.args.get("order", "desc")
        limit = int_param("limit", 50, 1, 500)
        offset = int_param("offset", 0, 0)
        if query:
            files = store.search_md_files(con, query, path_filter=path_filter, lang_filter=lang_filter, limit=limit, offset=offset)
        else:
            files = store.list_md_files(con, path_filter=path_filter, lang_filter=lang_filter, sort=sort, order=order, limit=limit, offset=offset)
        total = store.count_md_files(con, query=query, path_filter=path_filter, lang_filter=lang_filter)
        for item in files:
            item.pop("content", None)
        return jsonify({"files": files, "total": total})

    @bp.route("/api/files/<int:file_id>")
    async def api_file_detail(file_id: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()
        md = store.get_md_file(con, file_id)
        if not md:
            return jsonify({"error": "not found"}), 404
        return jsonify(md)

    @bp.route("/api/stats")
    async def api_stats():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()
        total = store.count_md_files(con)
        row = con.execute("SELECT COALESCE(SUM(size), 0) FROM md_files WHERE is_deleted = 0").fetchone()
        return jsonify({"total_files": total, "total_size": row[0] if row else 0})

    @bp.route("/api/languages")
    async def api_languages():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()
        return jsonify({"languages": store.get_languages(con)})
