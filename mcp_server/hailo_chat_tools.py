"""MCP tools for Hailo Chat (conversation management + web search)."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


_PFX = "/ext/hailo-genai"


def register_hailo_chat_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Hailo Chat tools on the MCP server."""

    @mcp.tool()
    def hailo_chat_list(
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """List Hailo Chat conversations.

        Args:
            limit: Max conversations to return (default 50, max 200)
            offset: Pagination offset
        """
        limit = min(max(1, limit), 200)
        return _json(client.get(
            f"{_PFX}/api/chat/conversations",
            {"limit": str(limit), "offset": str(offset)},
        ))

    @mcp.tool()
    def hailo_chat_get(conversation_id: int) -> str:
        """Get a Hailo Chat conversation with all messages.

        Args:
            conversation_id: Conversation ID
        """
        if not isinstance(conversation_id, int) or conversation_id < 1:
            return _json({"error": "conversation_id must be a positive integer"})
        return _json(client.get(
            f"{_PFX}/api/chat/conversations/{conversation_id}",
        ))

    @mcp.tool()
    def hailo_chat_new(model: str = "qwen2.5-1.5b-chat") -> str:
        """Create a new Hailo Chat conversation.

        Args:
            model: LLM model name (default "qwen2.5-1.5b-chat")
        """
        return _json(client.post(
            f"{_PFX}/api/chat/new",
            {"model": model},
        ))

    @mcp.tool()
    def hailo_chat_rename(
        conversation_id: int,
        title: str,
    ) -> str:
        """Rename a Hailo Chat conversation.

        Args:
            conversation_id: Conversation ID
            title: New title
        """
        if not isinstance(conversation_id, int) or conversation_id < 1:
            return _json({"error": "conversation_id must be a positive integer"})
        if not title or not title.strip():
            return _json({"error": "title is required"})
        return _json(client.patch(
            f"{_PFX}/api/chat/conversations/{conversation_id}/title",
            {"title": title.strip()},
        ))

    @mcp.tool()
    def hailo_chat_delete(conversation_id: int) -> str:
        """Delete a Hailo Chat conversation.

        Args:
            conversation_id: Conversation ID to delete
        """
        if not isinstance(conversation_id, int) or conversation_id < 1:
            return _json({"error": "conversation_id must be a positive integer"})
        return _json(client.delete(
            f"{_PFX}/api/chat/conversations/{conversation_id}",
        ))

    @mcp.tool()
    def hailo_chat_active() -> str:
        """Get the currently active Hailo Chat conversation ID."""
        return _json(client.get(f"{_PFX}/api/chat/active"))

    @mcp.tool()
    def hailo_chat_send(
        content: str,
        conversation_id: int | None = None,
        model: str = "",
        vlm_model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 512,
        system_prompt: str = "",
        web_search: bool = False,
        file_id: int | None = None,
    ) -> str:
        """Send a message to Hailo Chat and get a response (waits for full completion).

        If `conversation_id` is omitted, a new conversation is created automatically.

        Args:
            content: User message text
            conversation_id: Existing conversation ID, or None to start a new conversation
            model: LLM model name (empty = server default)
            vlm_model: VLM model name used when an image is attached (empty = server default)
            temperature: Sampling temperature 0.0–1.0 (default 0.7)
            max_tokens: Maximum tokens to generate (default 512)
            system_prompt: System prompt override (default "You are a helpful assistant.")
            web_search: Whether to augment the prompt with DuckDuckGo search results
            file_id: Image file ID to attach for VLM inference (optional)
        """
        if not content or not content.strip():
            return _json({"error": "content is required"})
        body: dict = {
            "content": content.strip(),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "web_search": web_search,
        }
        if conversation_id is not None:
            if not isinstance(conversation_id, int) or conversation_id < 1:
                return _json({"error": "conversation_id must be a positive integer"})
            body["conversation_id"] = conversation_id
        if model:
            body["model"] = model
        if vlm_model:
            body["vlm_model"] = vlm_model
        if system_prompt:
            body["system_prompt"] = system_prompt
        if file_id is not None:
            if not isinstance(file_id, int) or file_id < 1:
                return _json({"error": "file_id must be a positive integer"})
            body["file_id"] = file_id
        return _json(client.post_sse(f"{_PFX}/api/chat/send", body))

    @mcp.tool()
    def hailo_chat_search(
        query: str,
        max_results: int = 5,
    ) -> str:
        """Perform a web search via DuckDuckGo for Hailo Chat context injection.

        Args:
            query: Search query
            max_results: Max results to return (default 5, max 10)
        """
        if not query or not query.strip():
            return _json({"error": "query is required"})
        max_results = min(max(1, max_results), 10)
        return _json(client.post(
            f"{_PFX}/api/chat/search",
            {"query": query.strip(), "max_results": max_results},
        ))
