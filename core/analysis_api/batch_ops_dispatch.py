"""Batch analysis dispatch and prompt trend operations.

Orchestrates batch AI analysis: validates input, resolves targets,
and dispatches to the appropriate execution path (worker, subprocess,
or background thread).
"""

import logging
import threading

import ai_analysis
from core.analysis_api.batch_runner import run_batch_analyze
from core.analysis_api.batch_targets import resolve_batch_targets
from core.analysis_api.config_ops import is_local_engine
from core.analysis_api.engine_resolver import _resolve_with_fallback
from core.configuration.api import load_config_json
from core.services_core.db_api import get_db

logger = logging.getLogger(__name__)


def start_batch_analysis(data: dict):
    """Start a batch AI analysis job based on request data.

    Routes to the appropriate backend: inference worker, Hailo subprocess,
    or in-process background thread.
    """
    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})
    raw_limit = int(data.get("limit", 10))

    if is_local_engine(ai_config):  # noqa: SIM108 — nested ternary would reduce readability
        limit = raw_limit  # 0 = all files
    else:
        limit = min(raw_limit, 10) if raw_limit > 0 else 10

    scan_root = data.get("scan_root", "")
    file_ids = resolve_batch_targets(data.get("file_ids", []), limit, scan_root)
    if not file_ids:
        return {"error": "分析対象のファイルがありません"}, 400

    if _try_submit_to_worker("ai_analysis", file_ids):
        return {"started": True, "count": len(file_ids), "worker": True}, 200

    # Hailo VLM holds the GIL during NPU inference, so running in
    # the main process thread would stall server responses.
    # Run in a separate process to avoid blocking the Quart web process.
    engine_type = ai_config.get("engine", "")
    if engine_type == "hailo_vlm":
        from core.analysis_api.batch_ops_hailo import (
            _cleanup_stale_hailo_job,
            _run_in_subprocess,
        )
        from core.jobs_core.jobs import job_manager
        try:
            job_manager.start("ai_analysis", "AI分析 (Hailo VLM)")
        except ValueError:
            # Clean up if subprocess has terminated but job still exists
            _cleanup_stale_hailo_job()
            try:
                job_manager.start("ai_analysis", "AI分析 (Hailo VLM)")
            except ValueError:
                return {"error": "AI分析が既に実行中です"}, 409
        _run_in_subprocess(file_ids)
        return {"started": True, "count": len(file_ids), "subprocess": True}, 200

    server_ids = data.get("server_ids") or None
    threading.Thread(
        target=lambda: run_batch_analyze(file_ids, server_ids=server_ids),
        daemon=True,
    ).start()
    parallel = len(server_ids) > 1 if server_ids else False
    return {"started": True, "count": len(file_ids), "parallel": parallel}, 200


def _try_submit_to_worker(job_id: str, file_ids: list) -> bool:
    """Submit task to inference worker if enabled and running. Returns False otherwise."""
    try:
        config = load_config_json(None)
        worker_cfg = config.get("inference_worker", {})
        if not worker_cfg.get("enabled", False):
            return False

        from core.inference_worker.bridge import inference_bridge
        if not inference_bridge.is_running:
            return False

        from core.jobs_core.jobs import job_manager
        job_manager.start(job_id, "AI分析")

        from core.inference_worker.task_types import InferenceTask, TaskType
        task = InferenceTask(
            task_id=job_id,
            task_type=TaskType.AI_ANALYSIS_BATCH,
            file_ids=file_ids,
            config={
                "ai_analysis": config.get("ai_analysis", {}),
                "video_analysis": config.get("video_analysis", {}),
            },
        )
        return inference_bridge.submit_task(task)
    except Exception:
        return False


def analyze_prompt_trends():
    """Analyze prompt trends across recent files."""
    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})
    engine_type, engine_kwargs, err = _resolve_with_fallback(ai_config)
    if err:
        return {"error": err}, 400

    con = get_db()
    rows = con.execute(
        """
        SELECT tm.raw_prompt as positive, tm.raw_negative as negative
        FROM templates tm JOIN files f ON f.id = tm.file_id
        WHERE f.is_deleted = 0 AND tm.raw_prompt IS NOT NULL
        ORDER BY f.mtime DESC LIMIT 50
    """
    )
    prompts = [{"positive": r["positive"], "negative": r["negative"]} for r in rows]
    engine = ai_analysis.get_engine(engine_type, **engine_kwargs)
    try:
        result = engine.analyze_prompt_trends(prompts)
    except RuntimeError as e:
        logger.warning("analysis.trends engine error: %s", e)
        return {"error": str(e)}, 200

    # Auto-save to history (best-effort, never block the response)
    try:
        from core.analysis_api.trend_history_ops import save_trend_history
        save_trend_history(engine_type, len(prompts), result)
    except Exception:
        # Best-effort by design -- the response still goes out -- but a history
        # that has quietly stopped being written looks like an idle system.
        logger.warning("trend history was not saved", exc_info=True)

    return {"success": True, "result": result}, 200
