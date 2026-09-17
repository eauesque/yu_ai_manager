"""Agent Safety Gateway API: Kill Switch, Circuit Breaker, Budget, Journal.

Core safety primitives for the agent system.
Route functions are registered onto the parent blueprint by agent_api.py.
"""

import logging

from quart import request

from core.infra_core.api_errors import api_result
from core.services_core.db_async import run_db_sync

logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_routes(bp):
    """Register core safety routes on the given blueprint."""

    # -- Kill Switch -----------------------------------------------------------

    @bp.route("/api/agent/kill", methods=["POST"])
    async def agent_kill():
        """Activate Kill Switch."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        reason = str(data.get("reason", "Manual kill via API"))

        from core.agent_safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.kill(reason)
        return api_result({"ok": True, "status": ks.status()})

    @bp.route("/api/agent/resume", methods=["POST"])
    async def agent_resume():
        """Deactivate Kill Switch."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.resume()
        return api_result({"ok": True, "status": ks.status()})

    @bp.route("/api/agent/status", methods=["GET"])
    async def agent_status():
        """Unified status: Kill Switch + Circuit Breaker + Budget + per-process states."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.kill_switch import get_kill_switch
        ks = get_kill_switch()

        result = {"kill_switch": ks.status()}

        try:
            from core.agent_safety.circuit_breaker import get_circuit_breaker
            result["circuit_breaker"] = get_circuit_breaker().status()
        except Exception:
            result["circuit_breaker"] = {"enabled": False, "state": "unknown"}

        # Import SESSION_ID separately so .status() failures don't overwrite it.
        SESSION_ID: str | None = None
        try:
            from mcp_server.interceptor import SESSION_ID as _sid
            SESSION_ID = _sid
        except Exception:
            logger.warning("agent API step failed", exc_info=True)
        try:
            from core.agent_safety.budget_tracker import get_budget_tracker
            result["budget"] = get_budget_tracker(SESSION_ID).status() if SESSION_ID else {}
        except Exception:
            result["budget"] = {}

        # Per-process states (SQLite shared tables, migration 76).
        # Shows MCP subprocess's CB state and budget usage alongside Web Server's in-memory values.
        try:
            from core.agent_safety.shared_state import read_all_budget_usages, read_all_cb_states
            cb_rows = read_all_cb_states()
            budget_rows = read_all_budget_usages(SESSION_ID) if SESSION_ID else []
            # Index by process_id for easy lookup
            processes: dict = {}
            for row in cb_rows:
                pid = row["process_id"]
                processes.setdefault(pid, {})["circuit_breaker"] = {
                    "state":         row["state"],
                    "open_reason":   row["open_reason"],
                    "failure_count": row["failure_count"],
                    "last_updated":  row["last_updated"],
                }
            for row in budget_rows:
                pid = row["process_id"]
                processes.setdefault(pid, {})["budget"] = {
                    "used_total":       row["used_total"],
                    "used_write":       row["used_write"],
                    "used_destructive": row["used_destructive"],
                    "last_updated":     row["last_updated"],
                }
            result["processes"] = processes
        except Exception as exc:
            logger.warning("agent_status processes read failed: %s", type(exc).__name__)
            result["processes"] = {}

        # Backward compat: expose kill_switch's killed flag at top level
        result["killed"] = result["kill_switch"]["killed"]
        result["reason"] = result["kill_switch"].get("reason", "")
        result["killed_at"] = result["kill_switch"].get("killed_at", "")

        return api_result(result)

    # -- Circuit Breaker -------------------------------------------------------

    @bp.route("/api/agent/circuit-breaker", methods=["GET"])
    async def circuit_breaker_status():
        """Get Circuit Breaker state."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.circuit_breaker import get_circuit_breaker
        return api_result(get_circuit_breaker().status())

    @bp.route("/api/agent/circuit-breaker/reset", methods=["POST"])
    async def circuit_breaker_reset():
        """Reset Circuit Breaker to closed state."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.circuit_breaker import get_circuit_breaker
        cb = get_circuit_breaker()
        cb.reset()
        return api_result({"ok": True, "status": cb.status()})

    # -- Budget ----------------------------------------------------------------

    @bp.route("/api/agent/budget", methods=["GET"])
    async def budget_status():
        """Get budget remaining."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.budget_tracker import get_budget_tracker
        from mcp_server.interceptor import SESSION_ID
        return api_result(get_budget_tracker(SESSION_ID).status())

    @bp.route("/api/agent/budget/reset", methods=["POST"])
    async def budget_reset():
        """Reset budget counter."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.agent_safety.budget_tracker import get_budget_tracker
        from mcp_server.interceptor import SESSION_ID
        bt = get_budget_tracker(SESSION_ID)
        bt.reset()
        return api_result({"ok": True, "status": bt.status()})

    # -- Journal ---------------------------------------------------------------

    @bp.route("/api/agent/journal", methods=["GET"])
    async def agent_journal():
        """Search Action Journal."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        tool_name = request.args.get("tool_name", "")
        status = request.args.get("status", "")
        session_id = request.args.get("session_id", "")
        try:
            limit = max(1, min(int(request.args.get("limit", "50")), 200))
        except (ValueError, TypeError):
            limit = 50
        try:
            offset = max(int(request.args.get("offset", "0")), 0)
        except (ValueError, TypeError):
            offset = 0

        def _search():
            from core.agent_safety.action_journal import search_journal
            return search_journal(
                tool_name=tool_name,
                status=status,
                session_id=session_id,
                limit=limit,
                offset=offset,
            )

        result = await run_db_sync(_search)
        return api_result(result)

    @bp.route("/api/agent/journal/stats", methods=["GET"])
    async def agent_journal_stats():
        """Get Action Journal statistics."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        def _stats():
            from core.agent_safety.action_journal import get_journal_stats
            return get_journal_stats()

        return api_result(await run_db_sync(_stats))
