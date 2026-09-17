import logging

from quart import request

from core.analysis_api.batch_ops_dispatch import (
    analyze_prompt_trends,
    start_batch_analysis,
)
from core.analysis_api.single_ops import (
    analyze_one_file,
    get_analysis_result,
)
from core.analysis_api.stats_ops import get_analysis_stats
from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_request import require_json_dict
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.services_core.db_async import run_db_sync

logger = logging.getLogger(__name__)

# /api/analysis/stats is COUNT/GROUP BY heavy on the analysis table; pure
# read with no per-request input. 60s TTL is fine since stats are advisory.
_ANALYSIS_STATS_CACHE = SimpleTTLCache(ttl_seconds=60.0, max_entries=2)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_analysis_job_routes(bp):
    @bp.route("/api/analysis/analyze/<int:file_id>", methods=["POST"])
    async def api_analysis_analyze(file_id):
        try:
            mode = "full"
            engine_override = None
            model_override = None
            server_id = None
            if request.is_json and await request.get_json(silent=True):
                body = await request.get_json(silent=True)
                mode = body.get("mode", "full")
                engine_override = body.get("engine") or None
                model_override = body.get("model") or None
                server_id = body.get("server_id")
            payload, status = await run_db_sync(
                analyze_one_file,
                file_id,
                mode=mode,
                engine_override=engine_override,
                model_override=model_override,
                server_id=server_id,
            )
            return api_result(payload, status)
        except Exception:
            logger.exception("analysis.analyze error for file_id=%d", file_id)
            return api_error("Analysis failed", 500)

    @bp.route("/api/analysis/result/<int:file_id>")
    async def api_analysis_result(file_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            payload, status = await run_db_sync(get_analysis_result, file_id)
            return api_result(payload, status)
        except Exception:
            logger.exception("analysis.result error for file_id=%d", file_id)
            return api_error("Failed to get analysis result", 500)

    @bp.route("/api/analysis/batch", methods=["POST"])
    async def api_analysis_batch():
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        payload, status = await run_db_sync(start_batch_analysis, data)
        return api_result(payload, status)

    @bp.route("/api/analysis/batch/cancel", methods=["POST"])
    async def api_analysis_batch_cancel():
        from core.jobs_core.jobs import job_manager

        if job_manager.cancel_job("ai_analysis"):
            return api_result({"status": "cancelling", "message": "AI analysis cancel requested"})
        return api_error("No running AI analysis job", 404, code="job_not_running")

    @bp.route("/api/analysis/trends", methods=["POST"])
    async def api_analysis_trends():
        try:
            payload, status = await run_db_sync(analyze_prompt_trends)
            return api_result(payload, status)
        except Exception:
            logger.exception("analysis.trends error")
            return api_error("Trend analysis failed", 500)

    @bp.route("/api/analysis/stats")
    async def api_analysis_stats():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        cached = _ANALYSIS_STATS_CACHE.peek("payload")
        if cached is not None:
            payload, status = cached
            return api_result(payload, status)
        try:
            payload, status = await run_db_sync(get_analysis_stats)
            if status == 200:
                _ANALYSIS_STATS_CACHE.put("payload", (payload, status))
            return api_result(payload, status)
        except Exception:
            logger.exception("analysis.stats error")
            return api_error("Failed to get analysis stats", 500)
