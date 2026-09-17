"""Search-oriented Chatlog MCP tools."""

from mcp.server.fastmcp import FastMCP

from .chatlog_tools_common import _PFX, as_json
from .client import YuManagerClient
from .validators import validate_search_limit


def _validate_conversation_id(conversation_id: int) -> str:
    if not isinstance(conversation_id, int) or conversation_id < 1:
        return "Error: conversation_id must be a positive integer"
    return ""


def register_chatlog_search_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Chatlog search tools on the MCP server."""

    @mcp.tool()
    def search_chat_logs(
        query: str = "",
        source: str = "",
        model: str = "",
        date_from: int = 0,
        date_to: int = 0,
        after: str = "",
        before: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """Search chat conversations using FTS5 full-text search."""
        limit, _ = validate_search_limit(limit)
        params = {"limit": str(limit), "offset": str(offset)}
        if query:
            params["query"] = query
        if source:
            params["source"] = source
        if model:
            params["model"] = model
        if date_from:
            params["date_from"] = str(date_from)
        if date_to:
            params["date_to"] = str(date_to)
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        return as_json(client.get(f"{_PFX}/api/conversations", params))

    @mcp.tool()
    def search_chat_logs_grouped(query: str, source: str = "", limit: int = 20) -> str:
        """Search chat messages grouped by conversation."""
        if not query.strip():
            return "Error: query must not be empty"
        limit, _ = validate_search_limit(limit)
        params = {"query": query, "group_by": "conversation", "limit": str(limit)}
        if source:
            params["source"] = source
        return as_json(client.get(f"{_PFX}/api/search", params))

    @mcp.tool()
    def get_conversation(conversation_id: int) -> str:
        """Get full conversation detail including all messages."""
        err = _validate_conversation_id(conversation_id)
        if err:
            return err
        return as_json(client.get(f"{_PFX}/api/conversations/{conversation_id}"))

    @mcp.tool()
    def find_chat_by_entity(entity_type: str, entity_value: str, limit: int = 50) -> str:
        """Find conversations containing a specific entity."""
        entity_type = entity_type.strip()
        entity_value = entity_value.strip()
        if not entity_type or not entity_value:
            return "Error: entity_type and entity_value are required"
        limit, _ = validate_search_limit(limit)
        return as_json(client.get(f"{_PFX}/api/entities/search", {"type": entity_type, "value": entity_value, "limit": str(limit)}))

    @mcp.tool()
    def get_related_conversations(conversation_id: int, limit: int = 10) -> str:
        """Get conversations related to a given conversation by shared entities."""
        err = _validate_conversation_id(conversation_id)
        if err:
            return err
        limit = max(1, min(limit, 50))
        return as_json(client.get(f"{_PFX}/api/conversations/{conversation_id}/related", {"limit": str(limit)}))

    @mcp.tool()
    def get_chat_summary(conversation_id: int, generate: bool = False) -> str:
        """Get the AI-generated summary of a conversation.

        Args:
            conversation_id: ID of the conversation.
            generate: If True, trigger on-demand AI generation when no summary
                exists yet (passes ``?generate=1`` to the API).
        """
        err = _validate_conversation_id(conversation_id)
        if err:
            return err
        params: dict[str, str] | None = None
        if generate:
            params = {"generate": "1"}
        return as_json(client.get(f"{_PFX}/api/conversations/{conversation_id}/summary", params))

    @mcp.tool()
    def get_chat_full(conversation_id: int) -> str:
        """Get full conversation with all messages."""
        err = _validate_conversation_id(conversation_id)
        if err:
            return err
        return as_json(client.get(f"{_PFX}/api/conversations/{conversation_id}"))

    @mcp.tool()
    def search_chat_by_topic(topic: str, limit: int = 50) -> str:
        """Search conversations by AI-extracted topic keywords."""
        if not topic.strip():
            return "Error: topic must not be empty"
        limit, _ = validate_search_limit(limit)
        return as_json(client.get(f"{_PFX}/api/chat/topics/search", {"q": topic, "limit": str(limit)}))

    @mcp.tool()
    def get_chat_decisions(conversation_id: int) -> str:
        """Get AI-extracted decisions from a conversation."""
        err = _validate_conversation_id(conversation_id)
        if err:
            return err
        return as_json(client.get(f"{_PFX}/api/chat/decisions", {"conversation_id": str(conversation_id)}))

    @mcp.tool()
    def search_decisions(query: str, limit: int = 50) -> str:
        """Search AI-extracted decisions across all conversations."""
        if not query.strip():
            return "Error: query must not be empty"
        limit, _ = validate_search_limit(limit)
        return as_json(client.get(f"{_PFX}/api/chat/decisions/search", {"q": query, "limit": str(limit)}))

    @mcp.tool()
    def list_conversations(
        query: str = "",
        source: str = "",
        model: str = "",
        after: str = "",
        before: str = "",
        date_from: int = 0,
        date_to: int = 0,
        sort: str = "updated_at",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """List conversations with optional filter and pagination.

        Args:
            query: Full-text filter applied to conversation title/messages.
            source: Filter by source (e.g. ``claude``, ``chatgpt``).
            model: Filter by model name.
            after: ISO 8601 date string — return conversations updated after
                this date (e.g. ``2026-01-01``).
            before: ISO 8601 date string — return conversations updated before
                this date.
            date_from: UNIX timestamp lower bound (alternative to ``after``).
            date_to: UNIX timestamp upper bound (alternative to ``before``).
            sort: Sort field; one of ``updated_at`` (default), ``created_at``,
                ``title``.
            limit: Maximum number of results (1–500, default 50).
            offset: Pagination offset (default 0).
        """
        limit, _ = validate_search_limit(limit)
        params: dict[str, str] = {"limit": str(limit), "offset": str(offset), "sort": sort}
        if query:
            params["query"] = query
        if source:
            params["source"] = source
        if model:
            params["model"] = model
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if date_from:
            params["date_from"] = str(date_from)
        if date_to:
            params["date_to"] = str(date_to)
        return as_json(client.get(f"{_PFX}/api/conversations", params))

    @mcp.tool()
    def search_chat_messages(
        query: str,
        source: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """Search individual chat messages using full-text search.

        Returns a flat list of matching messages (not grouped by conversation).
        Use ``search_chat_logs_grouped`` when you need results grouped by
        conversation instead.

        Args:
            query: Search query (required).
            source: Optional source filter (e.g. ``claude``, ``chatgpt``).
            limit: Maximum number of results (1–200, default 50).
            offset: Pagination offset (default 0).
        """
        if not query.strip():
            return "Error: query must not be empty"
        limit, _ = validate_search_limit(limit)
        params: dict[str, str] = {"query": query, "limit": str(limit), "offset": str(offset)}
        if source:
            params["source"] = source
        return as_json(client.get(f"{_PFX}/api/search", params))

    @mcp.tool()
    def text_search(
        query: str,
        target: str = "md,chat,prompt",
        limit: int = 20,
    ) -> str:
        """Cross-text search across markdown notes, chat logs, and prompts.

        Args:
            query: Search query (required).
            target: Comma-separated list of search targets. Valid values:
                ``md`` (markdown notes), ``chat`` (chat logs), ``prompt``
                (saved prompts). Default is all three: ``md,chat,prompt``.
            limit: Maximum number of results (1–200, default 20).
        """
        if not query.strip():
            return "Error: query must not be empty"
        limit = max(1, min(limit, 200))
        params: dict[str, str] = {"q": query, "target": target, "limit": str(limit)}
        return as_json(client.get(f"{_PFX}/api/text-search", params))

    @mcp.tool()
    def get_conversation_entities(conversation_id: int) -> str:
        """List entities extracted from a conversation.

        Returns named entities (people, projects, bugs, dates, etc.) that were
        extracted from the conversation by the AI preprocessing step.

        Args:
            conversation_id: ID of the conversation.
        """
        err = _validate_conversation_id(conversation_id)
        if err:
            return err
        return as_json(client.get(f"{_PFX}/api/conversations/{conversation_id}/entities"))
