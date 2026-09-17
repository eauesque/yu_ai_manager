"""Undo and anomaly review tools for agent safety."""

from .agent_safety_tools_common import as_json


def register_agent_safety_review_tools(mcp, client):
    """Register undo and anomaly tools."""

    @mcp.tool()
    def agent_undo(journal_id: int) -> str:
        """Undo a previous agent action by its journal ID.

        Only reversible actions (rate_images, set_tags, set_annotations,
        add_to_collection, remove_from_collection, create_collection,
        create_prompt) can be undone.

        Args:
            journal_id: The journal entry ID to undo (from agent_journal)
        """
        return as_json(client.post(f"/api/agent/undo/{journal_id}", {}))

    @mcp.tool()
    def agent_undoable(session_id: str = "", limit: int = 50) -> str:
        """List actions that can be undone.

        Args:
            session_id: Filter by session ID (optional)
            limit: Max results (default 50)
        """
        params = {"limit": str(min(max(1, limit), 200))}
        if session_id:
            params["session_id"] = session_id
        return as_json(client.get("/api/agent/undoable", params))

    @mcp.tool()
    def agent_anomaly_status() -> str:
        """Get anomaly detection status: alert counts, elevated state, recent alerts."""
        return as_json(client.get("/api/agent/anomaly"))

    @mcp.tool()
    def agent_anomaly_alerts(limit: int = 50) -> str:
        """Get anomaly detection alert history.

        Args:
            limit: Max alerts to return (default 50)
        """
        return as_json(client.get("/api/agent/anomaly/alerts", {"limit": str(limit)}))

    @mcp.tool()
    def agent_anomaly_reset() -> str:
        """Reset anomaly detection history and alerts."""
        return as_json(client.post("/api/agent/anomaly/reset", {}))

    @mcp.tool()
    def agent_audit_log(limit: int = 100, severity: str = "") -> str:
        """Get agent audit log entries.

        Args:
            limit: Max records to return (default 100)
            severity: Filter by severity level (e.g. "error", "warning", "info"). Empty = all.
        """
        params: dict = {"limit": limit}
        if severity:
            params["severity"] = severity
        return as_json(client.get("/api/agent/audit/log", params))

    @mcp.tool()
    def agent_audit_acknowledge(audit_id: int) -> str:
        """Acknowledge an audit log entry.

        Args:
            audit_id: Audit log entry ID to acknowledge
        """
        return as_json(client.post(f"/api/agent/audit/acknowledge/{int(audit_id)}", {}))

    @mcp.tool()
    def agent_audit_verify() -> str:
        """Verify the integrity of the audit log hash chain."""
        return as_json(client.get("/api/agent/audit/verify"))

    @mcp.tool()
    def agent_audit_report(hours: int = 24) -> str:
        """Generate an audit summary report.

        Args:
            hours: Hours of history to include (default 24)
        """
        return as_json(client.post("/api/agent/audit/report", {"hours": hours}))
