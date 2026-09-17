"""MCP tools for task scheduler management."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_scheduler_tools(mcp: FastMCP, client: YuManagerClient):
    """Register scheduler management tools on the MCP server."""

    @mcp.tool()
    def get_scheduler_status() -> str:
        """Get task scheduler status: running state, registered jobs, next run times."""
        return _json(client.get("/api/scheduler/status"))

    @mcp.tool()
    def list_scheduled_jobs() -> str:
        """List all scheduled jobs with their triggers and next run times."""
        return _json(client.get("/api/scheduler/jobs"))

    @mcp.tool()
    def trigger_scheduled_job(job_id: str) -> str:
        """Trigger immediate execution of a scheduled job.

        Args:
            job_id: Job ID to trigger (e.g. "db_vacuum", "db_integrity_check", "thumbnail_cleanup")
        """
        if not job_id or not job_id.strip():
            return _json({"error": "job_id is required"})
        return _json(client.post(f"/api/scheduler/jobs/{job_id.strip()}/trigger", {}))

    @mcp.tool()
    def pause_scheduled_job(job_id: str) -> str:
        """Pause a scheduled job (stops automatic execution).

        Args:
            job_id: Job ID to pause
        """
        if not job_id or not job_id.strip():
            return _json({"error": "job_id is required"})
        return _json(client.post(f"/api/scheduler/jobs/{job_id.strip()}/pause", {}))

    @mcp.tool()
    def resume_scheduled_job(job_id: str) -> str:
        """Resume a paused scheduled job.

        Args:
            job_id: Job ID to resume
        """
        if not job_id or not job_id.strip():
            return _json({"error": "job_id is required"})
        return _json(client.post(f"/api/scheduler/jobs/{job_id.strip()}/resume", {}))

    @mcp.tool()
    def get_scheduler_history() -> str:
        """Get recent execution history of scheduled jobs (newest first, max 100)."""
        return _json(client.get("/api/scheduler/history"))

    @mcp.tool()
    def create_scheduled_job(
        job_id: str,
        func_name: str,
        trigger: str = "cron",
        trigger_args: dict | None = None,
    ) -> str:
        """Create a new scheduled job.

        Args:
            job_id: Unique job identifier
            func_name: Fully qualified function name to execute (e.g. "core.scheduler_core.builtin_jobs.vacuum_db")
            trigger: Trigger type — "cron", "interval", or "date"
            trigger_args: Trigger-specific arguments (e.g. {"hour": 3, "minute": 0} for cron)
        """
        job_id = job_id.strip()
        func_name = func_name.strip()
        if not job_id or not func_name:
            return _json({"error": "job_id and func_name are required"})
        payload: dict = {
            "job_id": job_id,
            "func_name": func_name,
            "trigger": trigger,
            "trigger_args": trigger_args or {},
        }
        return _json(client.post("/api/scheduler/jobs", payload))

    @mcp.tool()
    def delete_scheduled_job(job_id: str) -> str:
        """Delete a scheduled job permanently.

        Args:
            job_id: Job ID to delete
        """
        job_id = job_id.strip()
        if not job_id:
            return _json({"error": "job_id is required"})
        return _json(client.delete(f"/api/scheduler/jobs/{job_id}"))
