"""Scan wait tools for MCP."""

from mcp.server.fastmcp import Context, FastMCP

from .client import YuManagerClient
from .wait_tools_common import DEFAULT_TIMEOUT, as_json, clamp_timeout, poll_jobs


def register_wait_scan_tools(mcp: FastMCP, client: YuManagerClient):
    """Register scan wait tools."""

    @mcp.tool()
    async def wait_for_scan(timeout: int = DEFAULT_TIMEOUT, ctx: Context = None) -> str:
        """Wait for a running scan to complete. Returns final status.

        Sends real-time progress notifications to clients that support
        MCP notifications (progressToken). Non-supporting clients receive
        the final result after blocking wait.

        Args:
            timeout: Max seconds to wait (default 600, max 3600)
        """
        timeout = clamp_timeout(timeout)
        status = client.get("/api/jobs/status")
        scan_job_id = next((job.get("job_id", "") for job in status.get("active", []) if job.get("job_id", "") in ("scan", "scan-all")), "")
        if not scan_job_id:
            recent_job = next((job for job in status.get("recent", []) if job.get("job_id", "") in ("scan", "scan-all")), None)
            if recent_job:
                return as_json({"ok": True, "status": "already_completed", "job": recent_job})
            return as_json({"ok": True, "status": "no_scan", "message": "実行中のスキャンがありません"})
        return await poll_jobs(ctx, client, scan_job_id, timeout, "スキャン")
