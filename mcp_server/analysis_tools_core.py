"""Core image analysis MCP tools."""

from mcp.server.fastmcp import FastMCP

from .analysis_tools_common import as_json
from .client import YuManagerClient
from .validators import validate_file_id


def register_analysis_core_tools(mcp: FastMCP, client: YuManagerClient):
    """Register core AI analysis tools."""

    @mcp.tool()
    def analyze_image(file_id: int) -> str:
        """Run AI analysis on a single image to generate a description."""
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.post(f"/api/analysis/analyze/{file_id}", {}))

    @mcp.tool()
    def analyze_batch(file_ids: list, expected_count: int = 0, server_ids: list | None = None) -> str:
        """Run AI analysis on multiple files at once."""
        from .validators import check_batch_all_failed, validate_batch_size
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        payload = {"file_ids": file_ids}
        if server_ids:
            payload["server_ids"] = server_ids
        return as_json(check_batch_all_failed(client.post("/api/analysis/batch", payload)))

    @mcp.tool()
    def analyze_batch_cancel() -> str:
        """Cancel a running AI analysis batch job."""
        return as_json(client.post("/api/analysis/batch/cancel", {}))

    @mcp.tool()
    def get_analysis_result(file_id: int) -> str:
        """Get AI analysis result for a specific file."""
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.get(f"/api/analysis/result/{file_id}"))

    @mcp.tool()
    def get_analysis_stats() -> str:
        """Get AI analysis statistics."""
        return as_json(client.get("/api/analysis/stats"))

    @mcp.tool()
    def analyze_prompt_trends(limit: int = 100) -> str:
        """Run prompt trend analysis."""
        return as_json(client.post("/api/analysis/trends", {"limit": limit}))

    @mcp.tool()
    def get_trend_history(limit: int = 20) -> str:
        """Get past prompt trend analysis results."""
        return as_json(client.get("/api/analysis/trends/history", {"limit": str(limit)}))

    @mcp.tool()
    def delete_trend_history(history_id: int) -> str:
        """Delete a prompt trend analysis history entry."""
        return as_json(client.delete(f"/api/analysis/trends/history/{history_id}"))
