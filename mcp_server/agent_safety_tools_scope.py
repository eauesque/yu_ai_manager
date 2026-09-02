"""Approval, scope, and auto-approve tools for agent safety."""

from .agent_safety_tools_common import as_json


def register_agent_safety_scope_tools(mcp, client):
    """Register approval and scope tools."""

    @mcp.tool()
    def agent_approval_status() -> str:
        """Get pending approval requests and recent approval history."""
        return as_json(client.get("/api/agent/approval"))

    @mcp.tool()
    def agent_scope_status() -> str:
        """Get Scope Fence status: active scopes, available presets."""
        return as_json(client.get("/api/agent/scope"))

    @mcp.tool()
    def agent_scope_set(preset: str = "organizer", duration_hours: float = 0) -> str:
        """Set the scope for the current MCP session.

        Controls which tools are allowed/denied. Presets:
        - read_only: View only, all writes blocked
        - tagger: Tags and annotations only
        - organizer: Ratings, tags, collections (no deletes)
        - full_access: All operations (destructive still needs approval)

        Args:
            preset: Scope preset name
            duration_hours: Session time limit in hours (0 = unlimited)
        """
        from .interceptor import SESSION_ID
        body = {"preset": preset}
        if duration_hours > 0:
            body["duration_hours"] = duration_hours
        return as_json(client.post(f"/api/agent/scope/{SESSION_ID}", body))

    @mcp.tool()
    def agent_tool_level(tool_name: str = "") -> str:
        """Check the safety level of a tool (auto/notify/approve).

        Args:
            tool_name: Tool name to check. If empty, returns full classification summary.
        """
        params = {}
        if tool_name:
            params["tool"] = tool_name
        return as_json(client.get("/api/agent/tool-levels", params))

    @mcp.tool()
    def agent_auto_approve_list() -> str:
        """List all auto-approve rules for Level 2 tools."""
        return as_json(client.get("/api/agent/auto-approve"))

    @mcp.tool()
    def agent_auto_approve_add(tool_name: str) -> str:
        """Add an auto-approve rule for a Level 2 tool (always allow without user confirmation).

        Args:
            tool_name: Tool name to auto-approve
        """
        return as_json(client.post("/api/agent/auto-approve", {"tool": tool_name}))

    @mcp.tool()
    def agent_auto_approve_remove(index: int) -> str:
        """Remove an auto-approve rule by index.

        Args:
            index: Rule index (0-based, from agent_auto_approve_list)
        """
        return as_json(client.delete(f"/api/agent/auto-approve/{index}"))

    @mcp.tool()
    def agent_approval_respond(request_id: str, action: str) -> str:
        """Respond to a pending agent approval request.
        Args:
            request_id: Approval request ID
            action: "allow", "deny", or "always_allow"
        """
        return as_json(client.post(f"/api/agent/approval/{request_id}", {"action": action}))

    @mcp.tool()
    def agent_approval_history(limit: int = 50) -> str:
        """Get agent approval request history.
        Args:
            limit: Max entries (default 50)
        """
        return as_json(client.get("/api/agent/approval/history", {"limit": str(limit)}))

    @mcp.tool()
    def agent_scope_get(session_id: str) -> str:
        """Get scope fence for a specific session.
        Args:
            session_id: Session ID
        """
        return as_json(client.get(f"/api/agent/scope/{session_id}"))

    @mcp.tool()
    def agent_scope_delete(session_id: str) -> str:
        """Delete scope fence for a session.
        Args:
            session_id: Session ID
        """
        return as_json(client.delete(f"/api/agent/scope/{session_id}"))
