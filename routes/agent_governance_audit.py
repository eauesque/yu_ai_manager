from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_audit_routes(bp):
    @bp.route("/api/agent/anomaly", methods=["GET"])
    async def anomaly_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.anomaly_detector import get_anomaly_detector
        return api_result(get_anomaly_detector().status())

    @bp.route("/api/agent/anomaly/alerts", methods=["GET"])
    async def anomaly_alerts():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            limit = min(int(request.args.get("limit", "50")), 200)
        except (ValueError, TypeError):
            limit = 50
        from core.agent_safety.anomaly_detector import get_anomaly_detector
        return api_result({"alerts": get_anomaly_detector().get_alerts(limit)})

    @bp.route("/api/agent/anomaly/reset", methods=["POST"])
    async def anomaly_reset():
        from core.agent_safety.anomaly_detector import get_anomaly_detector
        get_anomaly_detector().reset()
        return api_result({"ok": True})

    @bp.route("/api/agent/audit", methods=["GET"])
    async def audit_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.audit_bureau import get_audit_bureau
        return api_result({"data": await run_db_sync(lambda: get_audit_bureau().status())})

    @bp.route("/api/agent/audit/log", methods=["GET"])
    async def audit_log():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        event_type = request.args.get("event_type", "")
        severity = request.args.get("severity", "")
        source = request.args.get("source", "")
        unacked = request.args.get("unacknowledged", "").lower() in ("1", "true")
        try:
            limit = min(int(request.args.get("limit", "50")), 200)
        except (ValueError, TypeError):
            limit = 50
        try:
            offset = max(int(request.args.get("offset", "0")), 0)
        except (ValueError, TypeError):
            offset = 0

        def _search():
            from core.agent_safety.audit_bureau import get_audit_bureau
            return get_audit_bureau().search_log(
                event_type=event_type,
                severity=severity,
                source=source,
                unacknowledged_only=unacked,
                limit=limit,
                offset=offset,
            )

        return api_result({"data": await run_db_sync(_search)})

    @bp.route("/api/agent/audit/acknowledge/<int:audit_id>", methods=["POST"])
    async def audit_acknowledge(audit_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        def _ack():
            from core.agent_safety.audit_bureau import get_audit_bureau
            return get_audit_bureau().acknowledge(audit_id)
        ok = await run_db_sync(_ack)
        if ok:
            return api_result({"ok": True, "audit_id": audit_id})
        return api_error("Audit log entry not found or already acknowledged", 404)

    @bp.route("/api/agent/audit/verify", methods=["GET"])
    async def audit_verify():
        """Verify the hash chain integrity of the audit_log table."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.services_core.agent_audit_service import verify_audit_log_chain

        return api_result(await run_db_sync(verify_audit_log_chain))

    @bp.route("/api/agent/audit/report", methods=["POST"])
    async def audit_report():
        data = await request.get_json(silent=True) or {}
        try:
            hours = min(int(data.get("hours", 24)), 720)
        except (ValueError, TypeError):
            hours = 24

        def _report():
            from core.agent_safety.audit_bureau import get_audit_bureau
            return get_audit_bureau().generate_report(hours)

        return api_result({"data": await run_db_sync(_report)})
