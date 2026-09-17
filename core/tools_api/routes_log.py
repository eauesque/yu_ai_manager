"""Route registration for debug log viewer API."""


from quart import request, send_file

from core.infra_core.api_errors import api_result
from core.infra_core.debug_log import get_debug_log_path, is_debug_enabled
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local


def register_tools_log_routes(bp):
    """Register debug log viewer routes."""

    @bp.route("/api/tools/debug-log")
    async def api_tools_debug_log():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        blocked = _require_local("Log view")
        if blocked:
            return blocked
        if not is_debug_enabled():
            return api_result({"enabled": False, "lines": []})

        log_path = get_debug_log_path()
        if not log_path.exists():
            return api_result({
                "enabled": True,
                "lines": [],
                "total_lines": 0,
                "log_path": str(log_path),
                "log_size_kb": 0,
            })

        limit = request.args.get("limit", 200, type=int)
        limit = max(1, min(limit, 5000))
        filter_str = request.args.get("filter", "").strip()

        def _read_log():
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return {"error": f"Failed to read log: {e}"}, 500

            all_lines = text.splitlines()
            total = len(all_lines)

            filtered = all_lines
            if filter_str:
                filtered = [ln for ln in all_lines if filter_str in ln]

            lines = filtered[-limit:]
            size_kb = round(log_path.stat().st_size / 1024, 1)

            return {
                "enabled": True,
                "lines": lines,
                "total_lines": total,
                "log_path": str(log_path),
                "log_size_kb": size_kb,
            }, 200

        payload, status = await run_db_sync(_read_log)
        return api_result(payload, status)

    @bp.route("/api/tools/debug-log/download")
    async def api_tools_debug_log_download():
        blocked = _require_local("Log download")
        if blocked:
            return blocked

        if not is_debug_enabled():
            return api_result({"error": "Debug logging is not enabled"}, 400)

        log_path = get_debug_log_path()
        if not log_path.exists():
            return api_result({"error": "Log file not found"}, 404)

        return await send_file(
            str(log_path.resolve()),
            as_attachment=True,
            attachment_filename=log_path.name,
            mimetype="text/plain",
        )

    @bp.route("/api/tools/debug-log/clear", methods=["POST"])
    async def api_tools_debug_log_clear():
        blocked = _require_local("Log clear")
        if blocked:
            return blocked

        if not is_debug_enabled():
            return api_result({"error": "Debug logging is not enabled"}, 400)

        log_path = get_debug_log_path()
        if not log_path.exists():
            return api_result({"error": "Log file not found"}, 404)

        def _clear():
            log_path.write_text("", encoding="utf-8")

        try:
            await run_db_sync(_clear)
        except Exception as e:
            return api_result({"error": f"Failed to clear log: {e}"}, 500)

        return api_result({"success": True, "message": "Log cleared"})
