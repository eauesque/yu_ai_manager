"""MCP tools for webhook management."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_webhook_tools(mcp: FastMCP, client):
    """Register webhook management MCP tools."""

    @mcp.tool()
    def list_webhooks() -> str:
        """List all registered webhooks."""
        return _json(client.get("/api/webhooks"))

    @mcp.tool()
    def create_webhook(
        url: str,
        events: list,
        label: str = "",
    ) -> str:
        """Create a new webhook subscription.

        Args:
            url: Webhook endpoint URL (required)
            events: List of event types to subscribe to (required)
            label: Optional display label for the webhook
        """
        if not url.strip():
            return _err("url is required")
        if not events:
            return _err("events list is required")
        body = {"url": url, "events": events}
        if label:
            body["label"] = label
        return _json(client.post("/api/webhooks", body))

    @mcp.tool()
    def update_webhook(
        webhook_id: str,
        url: str = "",
        events: list | None = None,
        label: str = "",
        active: bool | None = None,
    ) -> str:
        """Update an existing webhook.

        Args:
            webhook_id: Webhook ID to update (required)
            url: New endpoint URL (empty = keep current)
            events: New event list (None = keep current)
            label: New display label (empty = keep current)
            active: Enable or disable the webhook (None = keep current)
        """
        body = {}
        if active is not None:
            body["active"] = active
        if url:
            body["url"] = url
        if events is not None:
            body["events"] = events
        if label:
            body["label"] = label
        if not body:
            return _err("No fields to update")
        return _json(client.put(f"/api/webhooks/{webhook_id}", body))

    @mcp.tool()
    def delete_webhook(webhook_id: str) -> str:
        """Delete a webhook subscription.

        Args:
            webhook_id: Webhook ID to delete (required)
        """
        return _json(client.delete(f"/api/webhooks/{webhook_id}"))

    @mcp.tool()
    def test_webhook(webhook_id: str) -> str:
        """Send a test event to a webhook endpoint.

        Args:
            webhook_id: Webhook ID to test (required)
        """
        return _json(client.post(f"/api/webhooks/{webhook_id}/test", {}))

    @mcp.tool()
    def get_webhook_deliveries(
        webhook_id: str = "",
        limit: int = 50,
    ) -> str:
        """Get webhook delivery history.

        Args:
            webhook_id: Filter by webhook ID (empty = all webhooks)
            limit: Maximum number of deliveries to return (default 50)
        """
        params = {}
        if webhook_id:
            params["webhook_id"] = webhook_id
        if limit != 50:
            params["limit"] = str(limit)
        return _json(client.get("/api/webhooks/deliveries", params or None))

    # -- Inbound webhook tools --

    @mcp.tool()
    def create_inbound_webhook(
        label: str = "",
        allowed_events: list | None = None,
    ) -> str:
        """Create an inbound webhook that accepts external triggers.

        Returns a token URL for external services to POST to.
        Events in allowed_events are the only event types the external
        service can trigger. Empty list = all events allowed.

        Args:
            label: Display label for the inbound webhook
            allowed_events: List of event types the webhook can trigger (empty = all)
        """
        body = {"label": label, "allowed_events": allowed_events or []}
        return _json(client.post("/api/webhooks/inbound", body))

    @mcp.tool()
    def list_inbound_webhooks() -> str:
        """List all registered inbound webhooks."""
        return _json(client.get("/api/webhooks/inbound"))

    @mcp.tool()
    def update_inbound_webhook(
        webhook_id: str,
        label: str = "",
        allowed_events: list | None = None,
        active: bool | None = None,
    ) -> str:
        """Update an inbound webhook.

        Args:
            webhook_id: Inbound webhook ID to update (required)
            label: New display label (empty = keep current)
            allowed_events: New allowed event list (None = keep current)
            active: Enable or disable (None = keep current)
        """
        body = {}
        if active is not None:
            body["active"] = active
        if label:
            body["label"] = label
        if allowed_events is not None:
            body["allowed_events"] = allowed_events
        if not body:
            return _err("No fields to update")
        return _json(client.put(f"/api/webhooks/inbound/{webhook_id}", body))

    @mcp.tool()
    def delete_inbound_webhook(webhook_id: str) -> str:
        """Delete an inbound webhook.

        Args:
            webhook_id: Inbound webhook ID to delete (required)
        """
        return _json(client.delete(f"/api/webhooks/inbound/{webhook_id}"))
