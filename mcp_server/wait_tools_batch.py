"""Batch wait tools for MCP."""

from mcp.server.fastmcp import Context, FastMCP

from .client import YuManagerClient
from .wait_tools_common import DEFAULT_TIMEOUT, as_json, clamp_timeout, poll_jobs


def register_wait_batch_tools(mcp: FastMCP, client: YuManagerClient):
    """Register batch wait tools."""

    @mcp.tool()
    async def wait_for_batch(job_id: str = "ai_analysis", timeout: int = DEFAULT_TIMEOUT, ctx: Context = None) -> str:
        """Wait for a batch job (AI analysis, WD-Tagger, etc.) to complete.

        Sends real-time progress notifications to clients that support
        MCP notifications (progressToken). Non-supporting clients receive
        the final result after blocking wait.

        Args:
            job_id: Job ID to wait for (default "ai_analysis"). Common values:
                    "ai_analysis", "wd_tagger_batch", "hash_backfill"
            timeout: Max seconds to wait (default 600, max 3600)
        """
        timeout = clamp_timeout(timeout)
        status = client.get("/api/jobs/status")
        found = any(job.get("job_id") == job_id for job in status.get("active", []))
        if not found:
            recent_job = next((job for job in status.get("recent", []) if job.get("job_id") == job_id), None)
            if recent_job:
                return as_json({"ok": True, "status": "already_completed", "job": recent_job})
            return as_json({"ok": True, "status": "no_job", "message": f"ジョブ '{job_id}' が見つかりません"})
        label = {"ai_analysis": "AI分析", "wd_tagger_batch": "WD-Tagger", "hash_backfill": "ハッシュ計算"}.get(job_id, job_id)
        return await poll_jobs(ctx, client, job_id, timeout, label)
