"""Bluesky queue and monitor tools for SNS MCP integration."""

from mcp.server.fastmcp import FastMCP

from .sns_share_tools_common import as_json


def register_sns_bluesky_tools(mcp: FastMCP, client):
    """Register Bluesky queue and monitor tools."""

    @mcp.tool()
    def bsky_get_pending_notifications() -> str:
        """Get pending Bluesky notifications from the local queue."""
        return as_json(client._request("GET", "/api/sns/bsky/queue/pending"))

    @mcp.tool()
    def bsky_get_notification_queue(status: str = "", notification_type: str = "") -> str:
        """Get Bluesky notification queue items with optional filters."""
        params = {}
        if status:
            params["status"] = status
        if notification_type:
            params["type"] = notification_type
        return as_json(client._request("GET", "/api/sns/bsky/queue", params=params))

    @mcp.tool()
    def bsky_triage_notification(queue_id: int, result: str) -> str:
        """Set triage result for a Bluesky notification."""
        if result not in ("valid", "invalid"):
            return as_json({"error": "result must be 'valid' or 'invalid'"})
        return as_json(client._request("POST", f"/api/sns/bsky/queue/{queue_id}/triage", body={"result": result}))

    @mcp.tool()
    def bsky_send_auto_response(queue_id: int, text: str) -> str:
        """Send an auto-response reply to a Bluesky mention/reply/quote."""
        if not text or not text.strip():
            return as_json({"error": "text is required"})
        return as_json(client._request("POST", f"/api/sns/bsky/queue/{queue_id}/respond", body={"text": text.strip()}))

    @mcp.tool()
    def bsky_poll_notifications() -> str:
        """Trigger immediate polling of Bluesky notifications."""
        return as_json(client._request("POST", "/api/sns/bsky/queue/poll", body={}))

    @mcp.tool()
    def bsky_get_monitor_config() -> str:
        """Get Bluesky monitor configuration."""
        return as_json(client._request("GET", "/api/sns/bsky/monitor/config"))

    @mcp.tool()
    def bsky_save_monitor_config(
        poll_interval_minutes: int = 0,
        auto_dismiss_follow: bool = True,
        auto_dismiss_like: bool = True,
        auto_dismiss_repost: bool = True,
        auto_respond_enabled: bool = False,
    ) -> str:
        """Update Bluesky monitor configuration."""
        body = {
            "auto_dismiss_follow": auto_dismiss_follow,
            "auto_dismiss_like": auto_dismiss_like,
            "auto_dismiss_repost": auto_dismiss_repost,
            "auto_respond_enabled": auto_respond_enabled,
        }
        if poll_interval_minutes > 0:
            body["poll_interval_minutes"] = poll_interval_minutes
        return as_json(client._request("PUT", "/api/sns/bsky/monitor/config", body=body))

    @mcp.tool()
    def bsky_get_triage_prompts() -> str:
        """Get Bluesky triage prompts and auto-response templates."""
        return as_json(client._request("GET", "/api/sns/bsky/monitor/triage-prompts"))

    @mcp.tool()
    def bsky_save_triage_prompts(
        triage_mention: str = "",
        triage_reply: str = "",
        triage_quote: str = "",
        response_mention: str = "",
        response_reply: str = "",
        response_quote: str = "",
    ) -> str:
        """Update Bluesky triage prompts and/or auto-response templates."""
        body = {}
        triage_prompts = {}
        if triage_mention:
            triage_prompts["mention"] = triage_mention
        if triage_reply:
            triage_prompts["reply"] = triage_reply
        if triage_quote:
            triage_prompts["quote"] = triage_quote
        if triage_prompts:
            body["triage_prompts"] = triage_prompts
        auto_responses = {}
        if response_mention:
            auto_responses["mention"] = response_mention
        if response_reply:
            auto_responses["reply"] = response_reply
        if response_quote:
            auto_responses["quote"] = response_quote
        if auto_responses:
            body["auto_responses"] = auto_responses
        if not body:
            return as_json({"error": "At least one value must be provided"})
        return as_json(client._request("PUT", "/api/sns/bsky/monitor/triage-prompts", body=body))
