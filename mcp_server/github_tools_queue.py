"""Queue tools for GitHub MCP integration."""

from mcp.server.fastmcp import FastMCP

from .github_tools_common import as_json


def register_github_queue_tools(mcp: FastMCP, client):
    """Register GitHub queue tools."""

    @mcp.tool()
    def github_get_pending_issues() -> str:
        """Get pending issues from the local issue queue."""
        return as_json(client._request("GET", "/api/github/queue/pending"))

    @mcp.tool()
    def github_get_issue_queue(status: str = "") -> str:
        """Get issue queue items with optional status filter."""
        params = {}
        if status:
            params["status"] = status
        return as_json(client._request("GET", "/api/github/queue", params=params))

    @mcp.tool()
    def github_triage_queue_item(queue_id: int, result: str) -> str:
        """Set triage result for a queued issue."""
        if result not in ("valid", "invalid"):
            return as_json({"error": "result must be 'valid' or 'invalid'"})
        return as_json(client._request("POST", f"/api/github/queue/{queue_id}/triage", body={"result": result}))

    @mcp.tool()
    def github_dismiss_queue_item(queue_id: int, auto_close: bool = False, account_label: str = "") -> str:
        """Dismiss a queued issue."""
        body = {"auto_close": auto_close}
        if account_label:
            body["account_label"] = account_label
        return as_json(client._request("POST", f"/api/github/queue/{queue_id}/dismiss", body=body))

    @mcp.tool()
    def github_poll_issues() -> str:
        """Trigger immediate polling of GitHub issues for all accounts."""
        return as_json(client._request("POST", "/api/github/queue/poll", body={}))

    @mcp.tool()
    def github_get_queue_config() -> str:
        """Get the issue queue configuration (poll interval, auto-close settings)."""
        return as_json(client._request("GET", "/api/github/queue/config"))

    @mcp.tool()
    def github_save_queue_config(
        poll_interval_minutes: int | None = None,
        auto_close_invalid: bool | None = None,
        notify_on_connect: bool | None = None,
    ) -> str:
        """Update the issue queue configuration.

        Args:
            poll_interval_minutes: How often to poll for new issues (minutes).
            auto_close_invalid: Automatically close issues marked invalid.
            notify_on_connect: Send notification when a new account connects.
        """
        body = {}
        if poll_interval_minutes is not None:
            body["poll_interval_minutes"] = poll_interval_minutes
        if auto_close_invalid is not None:
            body["auto_close_invalid"] = auto_close_invalid
        if notify_on_connect is not None:
            body["notify_on_connect"] = notify_on_connect
        if not body:
            return as_json({"error": "At least one config field must be provided"})
        return as_json(client._request("PUT", "/api/github/queue/config", body=body))
