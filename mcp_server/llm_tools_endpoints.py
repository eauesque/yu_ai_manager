"""Endpoint management tools for LLM MCP integration."""

from .llm_tools_common import as_error, as_json


def register_llm_endpoint_tools(mcp, client):
    @mcp.tool()
    def llm_endpoints_list() -> str:
        """List all configured LLM endpoints (API keys masked)."""
        return as_json(client.get("/api/settings/llm-endpoints"))

    @mcp.tool()
    def llm_endpoints_set(category: str, base_url: str, model: str, api_key: str = "", timeout: int = 60) -> str:
        """Add or update an LLM endpoint for a category.

        Args:
            category: Endpoint category (e.g. 'chat', 's2t_postprocess')
            base_url: OpenAI-compatible API base URL (e.g. 'http://localhost:11434/v1')
            model: Model name (e.g. 'llama3.2', 'gpt-4o-mini')
            api_key: API key (optional, encrypted on save)
            timeout: Request timeout in seconds
        """
        if not category.strip():
            return as_error("category is required")
        return as_json(client.put("/api/settings/llm-endpoints", body={
            "category": category,
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
            "timeout": timeout,
        }))

    @mcp.tool()
    def llm_endpoints_remove(category: str) -> str:
        """Remove an LLM endpoint.

        Args:
            category: Endpoint category to remove
        """
        return as_json(client.delete(f"/api/settings/llm-endpoints/{category}"))

    @mcp.tool()
    def llm_endpoints_test(base_url: str, api_key: str = "") -> str:
        """Test connection to an LLM endpoint.

        Args:
            base_url: OpenAI-compatible API base URL
            api_key: API key (optional)
        """
        return as_json(client.post("/api/settings/llm-endpoints/test", body={"base_url": base_url, "api_key": api_key}))
