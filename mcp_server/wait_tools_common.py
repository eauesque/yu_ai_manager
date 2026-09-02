"""Shared polling helpers for wait MCP tools."""

import asyncio
import contextlib
import json
import time

POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 600
MAX_TIMEOUT = 3600


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def clamp_timeout(timeout: int) -> int:
    return max(1, min(timeout, MAX_TIMEOUT))


async def poll_jobs(ctx, client, job_id: str, timeout: int, label: str) -> str:
    deadline = time.monotonic() + timeout
    last_progress = -1
    while time.monotonic() < deadline:
        status = client.get("/api/jobs/status")
        if status.get("ok") is False:
            return as_json({"ok": False, "error": status.get("error", "API error")})

        active_job = next((job for job in status.get("active", []) if job.get("job_id") == job_id), None)
        if active_job:
            current = active_job.get("current", 0)
            total = active_job.get("total", 0)
            message = active_job.get("message", "")
            percent = active_job.get("percent", 0)
            if percent != last_progress:
                last_progress = percent
                with contextlib.suppress(Exception):
                    await ctx.report_progress(progress=float(current), total=float(total) if total else None, message=f"{label}: {message}" if message else label)
                with contextlib.suppress(Exception):
                    await ctx.info(f"{label}: {percent}% ({current}/{total}) {message}")
        else:
            recent_job = next((job for job in status.get("recent", []) if job.get("job_id") == job_id), None)
            if recent_job:
                with contextlib.suppress(Exception):
                    await ctx.report_progress(progress=1.0, total=1.0, message=f"{label}: 完了 ({recent_job.get('phase', 'complete')})")
                return as_json({"ok": True, "status": "completed", "job": recent_job})
        await asyncio.sleep(POLL_INTERVAL)
    return as_json({"ok": False, "status": "timeout", "error": f"{label}: {timeout}秒でタイムアウト"})
