"""builtin-video-analysis Extension entrypoint.

Provides multi-keyframe video analysis via vision LLMs.
Results are stored in the shared analysis table.
"""

import logging

from quart import Blueprint, request

logger = logging.getLogger(__name__)
bp = Blueprint(
    "video_analysis_ext",
    __name__,
    template_folder="templates/video_analysis",
)


def _api_result(data, status=200):
    from quart import jsonify
    resp = jsonify({"data": data})
    resp.status_code = status
    return resp


def _get_config():
    """Get video analysis config from extension config."""
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value

    return {
        "keyframe_count": int(
            get_extension_config_value("builtin-video-analysis", "keyframe_count", 4)
        ),
        "strategy": get_extension_config_value(
            "builtin-video-analysis", "strategy", "uniform"
        ),
    }


_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".ts"}


@bp.route("/api/video-analysis/analyze/<int:file_id>", methods=["POST"])
async def api_analyze(file_id):
    """Analyze video file via multi-keyframe vision analysis.

    POST body (optional):
        {
            "engine": "ollama",
            "model": "llava:latest",
            "keyframe_count": 4,
            "strategy": "uniform"
        }
    """
    from core.web.auth_helpers import require_admin_scope as _require_admin_scope

    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    from core.services_core.db_async import run_db_sync

    def _lookup_path() -> str | None:
        from core.services_core.db_state import get_readonly_db

        con = get_readonly_db()
        row = con.execute(
            "SELECT path FROM files WHERE id=? AND is_deleted=0",
            (file_id,),
        ).fetchone()
        return row["path"] if row else None

    file_path = await run_db_sync(_lookup_path)
    if not file_path:
        return _api_result({"error": "File not found"}, 404)

    from pathlib import Path as P

    ext = P(file_path).suffix.lower()
    if ext not in _VIDEO_EXTS:
        return _api_result({"error": f"Not a video file ({ext})"}, 400)

    cfg = _get_config()

    body = await request.get_json(silent=True) or {}
    engine_override = body.get("engine", "")
    model_override = body.get("model", "")
    keyframe_count = body.get("keyframe_count", cfg["keyframe_count"])
    strategy = body.get("strategy", cfg["strategy"])

    try:
        from .core_impl.analyze import analyze_and_save

        # ffmpeg keyframe extraction + vision LLM call is multi-second blocking
        # I/O; offload to a worker thread so the event loop stays responsive.
        result = await run_db_sync(
            analyze_and_save,
            file_id=file_id,
            file_path=file_path,
            engine_override=engine_override,
            model_override=model_override,
            keyframe_count=keyframe_count,
            strategy=strategy,
        )
        return _api_result(result, 200)

    except RuntimeError as e:
        logger.error("Video analysis error for file_id=%d: %s", file_id, e)
        return _api_result({"error": "Video analysis failed"}, 500)
    except Exception:
        logger.exception("Unexpected error in video analysis for file_id=%d", file_id)
        return _api_result({"error": "Internal video analysis error"}, 500)


def get_blueprint():
    return bp


__all__ = ["get_blueprint"]
