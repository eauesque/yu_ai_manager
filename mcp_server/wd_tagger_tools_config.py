"""Model and config tools for WD-Tagger."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .wd_tagger_tools_common import as_json


def register_wd_tagger_config_tools(mcp: FastMCP, client: YuManagerClient):
    """Register WD-Tagger config and model tools."""

    @mcp.tool()
    def wd_tagger_model_status() -> str:
        """Check WD-Tagger model download status and availability."""
        return as_json(client.get("/api/wd-tagger/model/status"))

    @mcp.tool()
    def wd_tagger_get_config() -> str:
        """Get current WD-Tagger configuration (threshold, model, etc.)."""
        return as_json(client.get("/api/wd-tagger/config"))

    @mcp.tool()
    def wd_tagger_save_config(config: dict) -> str:
        """Save WD-Tagger configuration.
        Args:
            config: Config dict (threshold, model, etc.)
        """
        return as_json(client.post("/api/wd-tagger/config", config))

    @mcp.tool()
    def wd_tagger_download_model() -> str:
        """Download/update the WD-Tagger model."""
        return as_json(client.post("/api/wd-tagger/model/download", {}))
