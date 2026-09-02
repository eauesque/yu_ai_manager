from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_approval_routes(bp):
    @bp.route("/api/agent/approval", methods=["GET"])
    async def approval_pending():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.approval_gate import get_approval_gate
        return api_result(get_approval_gate().status())

    @bp.route("/api/agent/approval/<request_id>", methods=["POST"])
    async def approval_respond(request_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        decision = str(data.get("decision", ""))
        if decision not in ("allow", "deny", "always_allow"):
            return api_error("decision は allow/deny/always_allow のいずれかを指定してください", 400)
        from core.agent_safety.approval_gate import get_approval_gate
        ok = get_approval_gate().respond(request_id, decision)
        if not ok:
            return api_error("承認リクエストが見つからないか、既に応答済みです", 404)
        return api_result({"ok": True, "request_id": request_id, "decision": decision})

    @bp.route("/api/agent/approval/history", methods=["GET"])
    async def approval_history():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            limit = min(int(request.args.get("limit", "50")), 200)
        except (ValueError, TypeError):
            limit = 50
        from core.agent_safety.approval_gate import get_approval_gate
        return api_result({"history": get_approval_gate().get_history(limit)})

    @bp.route("/api/agent/undo/<int:journal_id>", methods=["POST"])
    async def undo_action(journal_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        def _undo():
            from core.agent_safety.undo_engine import execute_undo
            return execute_undo(journal_id)
        result = await run_db_sync(_undo)
        if result.get("ok"):
            return api_result(result)
        return api_error(result.get("message", "undo に失敗しました"), 400)

    @bp.route("/api/agent/undoable", methods=["GET"])
    async def undoable_actions():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        session_id = request.args.get("session_id", "")
        try:
            limit = min(int(request.args.get("limit", "50")), 200)
        except (ValueError, TypeError):
            limit = 50
        def _fetch():
            from core.agent_safety.undo_engine import get_undoable_actions
            return get_undoable_actions(session_id=session_id, limit=limit)
        items = await run_db_sync(_fetch)
        return api_result({"items": items, "count": len(items)})
