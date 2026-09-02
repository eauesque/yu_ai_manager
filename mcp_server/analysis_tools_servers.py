"""Server registry and config MCP tools for analysis."""

from mcp.server.fastmcp import FastMCP

from .analysis_tools_common import as_json
from .client import YuManagerClient


def register_analysis_server_tools(mcp: FastMCP, client: YuManagerClient):
    """Register server registry and config tools."""

    @mcp.tool()
    def get_analysis_config() -> str:
        """Get current AI analysis configuration."""
        return as_json(client.get("/api/analysis/config"))

    @mcp.tool()
    def list_ai_servers() -> str:
        """List all registered AI servers with their connection status."""
        return as_json(client.get("/api/analysis/servers"))

    @mcp.tool()
    def add_ai_server(name: str, type: str, config: dict, priority: int = 50, enabled: bool = True) -> str:
        """Register a new AI server."""
        return as_json(client.post("/api/analysis/servers", {"name": name, "type": type, "config": config, "priority": priority, "enabled": enabled}))

    @mcp.tool()
    def remove_ai_server(server_id: str) -> str:
        """Remove a registered AI server."""
        return as_json(client.delete(f"/api/analysis/servers/{server_id}"))

    @mcp.tool()
    def set_active_ai_server(server_id: str) -> str:
        """Switch the active AI server."""
        return as_json(client.post(f"/api/analysis/servers/{server_id}/activate", {}))

    @mcp.tool()
    def test_ai_server(server_id: str) -> str:
        """Test connection to a registered AI server."""
        return as_json(client.post(f"/api/analysis/servers/{server_id}/test", {}))

    @mcp.tool()
    def get_available_engines() -> str:
        """List available AI analysis engines with their models."""
        return as_json(client.get("/api/analysis/available-engines"))

    @mcp.tool()
    def save_analysis_config(config: dict) -> str:
        """Save AI analysis configuration."""
        return as_json(client.post("/api/analysis/config", config))

    @mcp.tool()
    def get_ollama_models() -> str:
        """List available Ollama models."""
        return as_json(client.get("/api/analysis/ollama/models"))

    @mcp.tool()
    def test_ollama_connection() -> str:
        """Test Ollama server connection."""
        return as_json(client.post("/api/analysis/ollama/test", {}))

    @mcp.tool()
    def get_openai_compat_models() -> str:
        """List available OpenAI-compatible API models."""
        return as_json(client.get("/api/analysis/openai-compat/models"))

    @mcp.tool()
    def test_openai_compat_connection() -> str:
        """Test OpenAI-compatible API connection."""
        return as_json(client.post("/api/analysis/openai-compat/test", {}))

    @mcp.tool()
    def update_ai_server(server_id: str, name: str = "", config: dict | None = None, priority: int = -1, enabled: bool = True) -> str:
        """Update an existing AI server configuration."""
        body = {"enabled": enabled}
        if name:
            body["name"] = name
        if config is not None:
            body["config"] = config
        if priority >= 0:
            body["priority"] = priority
        return as_json(client.put(f"/api/analysis/servers/{server_id}", body))

    @mcp.tool()
    def reorder_ai_servers(order: list) -> str:
        """Reorder AI servers by priority."""
        return as_json(client.put("/api/analysis/servers/reorder", {"order": order}))

    @mcp.tool()
    def migrate_ai_servers() -> str:
        """Migrate legacy analysis config to server registry format."""
        return as_json(client.post("/api/analysis/servers/migrate", {}))
