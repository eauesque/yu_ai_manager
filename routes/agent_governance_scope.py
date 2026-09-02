from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_scope_routes(bp):
    @bp.route("/api/agent/scope", methods=["GET"])
    async def scope_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.scope_fence import get_scope_fence
        return api_result(get_scope_fence().status())

    @bp.route("/api/agent/scope/<session_id>", methods=["GET"])
    async def scope_get(session_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.scope_fence import get_scope_fence
        scope = get_scope_fence().get_scope(session_id)
        if scope is None:
            return api_error("セッションスコープが見つかりません", 404)
        return api_result(scope)

    @bp.route("/api/agent/scope/<session_id>", methods=["POST"])
    async def scope_set(session_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        preset = str(data.get("preset", ""))
        denied = data.get("denied")
        name = str(data.get("name", ""))
        duration_hours = data.get("duration_hours")
        if denied is not None and not isinstance(denied, list):
            return api_error("denied はリストで指定してください", 400)
        from core.agent_safety.scope_fence import get_scope_fence
        fence = get_scope_fence()
        fence.set_scope(
            session_id=session_id,
            preset=preset,
            denied=denied,
            name=name,
            duration_hours=float(duration_hours) if duration_hours else None,
        )
        return api_result({"ok": True, "scope": fence.get_scope(session_id)})

    @bp.route("/api/agent/scope/<session_id>", methods=["DELETE"])
    async def scope_delete(session_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.scope_fence import get_scope_fence
        return api_result({"ok": get_scope_fence().remove_scope(session_id)})

    @bp.route("/api/agent/auto-approve", methods=["GET"])
    async def auto_approve_list():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.scope_fence import get_auto_approve_rules
        return api_result({"rules": get_auto_approve_rules()})

    @bp.route("/api/agent/auto-approve", methods=["POST"])
    async def auto_approve_add():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        tool_name = str(data.get("tool", ""))
        if not tool_name:
            return api_error("tool は必須です", 400)
        conditions = data.get("conditions")
        if conditions is not None and not isinstance(conditions, dict):
            return api_error("conditions は辞書で指定してください", 400)
        from core.agent_safety.scope_fence import add_auto_approve_rule
        return api_result({"ok": True, "rule": add_auto_approve_rule(tool_name, conditions)})

    @bp.route("/api/agent/auto-approve/<int:index>", methods=["DELETE"])
    async def auto_approve_delete(index):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.scope_fence import remove_auto_approve_rule
        ok = remove_auto_approve_rule(index)
        if not ok:
            return api_error("ルールが見つかりません", 404)
        return api_result({"ok": True})

    @bp.route("/api/agent/tool-levels", methods=["GET"])
    async def tool_levels():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.tool_classification import classify_name, get_all_overrides, get_classification_summary
        tool_name = request.args.get("tool", "")
        if tool_name:
            return api_result({"tool": tool_name, "level": classify_name(tool_name)})
        return api_result({"summary": get_classification_summary(), "overrides": get_all_overrides()})
