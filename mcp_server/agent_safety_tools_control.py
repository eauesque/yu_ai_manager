"""Kill switch, journal, and budget tools for agent safety."""

from .agent_safety_tools_common import as_json


def register_agent_safety_control_tools(mcp, client):
    """Register control and status tools."""

    @mcp.tool()
    def agent_kill(reason: str = "Manual kill via MCP") -> str:
        """Activate the Agent Kill Switch to immediately block all agent tool calls.

        Args:
            reason: Reason for activating the kill switch
        """
        return as_json(client.post("/api/agent/kill", {"reason": reason}))

    @mcp.tool()
    def agent_resume() -> str:
        """Deactivate the Agent Kill Switch to resume agent tool calls."""
        return as_json(client.post("/api/agent/resume", {}))

    @mcp.tool()
    def agent_status() -> str:
        """Check the current Agent Safety status (kill switch, circuit breaker, budget)."""
        return as_json(client.get("/api/agent/status"))

    @mcp.tool()
    def agent_journal(tool_name: str = "", status: str = "", session_id: str = "", limit: int = 50, offset: int = 0) -> str:
        """Search the agent action journal for recorded tool calls.

        Args:
            tool_name: Filter by tool name
            status: Filter by status (success, error, killed)
            session_id: Filter by session ID
            limit: Max results (1-200, default 50)
            offset: Skip first N results
        """
        params = {"limit": str(min(max(1, limit), 200)), "offset": str(max(0, offset))}
        if tool_name:
            params["tool_name"] = tool_name
        if status:
            params["status"] = status
        if session_id:
            params["session_id"] = session_id
        return as_json(client.get("/api/agent/journal", params))

    @mcp.tool()
    def agent_journal_stats() -> str:
        """Get agent action journal statistics: total actions, status breakdown, top tools."""
        return as_json(client.get("/api/agent/journal/stats"))

    @mcp.tool()
    def agent_circuit_breaker_status() -> str:
        """Get Circuit Breaker status: state (closed/open/half_open), counters, thresholds."""
        return as_json(client.get("/api/agent/circuit-breaker"))

    @mcp.tool()
    def agent_circuit_breaker_reset() -> str:
        """Reset the Circuit Breaker to closed state."""
        return as_json(client.post("/api/agent/circuit-breaker/reset", {}))

    @mcp.tool()
    def agent_budget_status() -> str:
        """Get Budget Tracker status: limits, used counts, remaining budget."""
        return as_json(client.get("/api/agent/budget"))

    @mcp.tool()
    def agent_budget_reset() -> str:
        """Reset the Budget Tracker counters for the current session."""
        return as_json(client.post("/api/agent/budget/reset", {}))
