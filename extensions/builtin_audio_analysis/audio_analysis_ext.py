"""builtin-audio-analysis Extension entrypoint.

Provides audio transcription via Whisper (local / API).
Results are stored in the shared analysis table.
"""

import asyncio
import logging

from quart import Blueprint, request

logger = logging.getLogger(__name__)
bp = Blueprint(
    "audio_analysis_ext",
    __name__,
    template_folder="templates/audio_analysis",
)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _api_result(data, status=200):
    from quart import jsonify
    resp = jsonify({"data": data})
    resp.status_code = status
    return resp


def _get_config():
    """Get audio analysis config from extension config + global config."""
    from core.configuration.json_rw import load_config_json
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value

    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})

    engine = get_extension_config_value("builtin-audio-analysis", "engine", "whisper_local")
    model = get_extension_config_value("builtin-audio-analysis", "whisper_model", "base")
    language = get_extension_config_value("builtin-audio-analysis", "whisper_language", "")

    # Whisper API uses the same OpenAI API key
    api_key = ai_config.get("openai_api_key", "")
    base_url = ""

    return {
        "engine": engine,
        "model": model,
        "language": language,
        "api_key": api_key,
        "base_url": base_url,
    }


@bp.route("/api/audio-analysis/transcribe/<int:file_id>", methods=["POST"])
async def api_transcribe(file_id):
    """Transcribe audio/video file and save to analysis table.

    POST body (optional):
        {"engine": "whisper_local"|"whisper_api", "model": "base", "language": "ja"}
    """
    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    row = con.execute(
        "SELECT path FROM files WHERE id=? AND is_deleted=0",
        (file_id,),
    ).fetchone()
    if not row:
        return _api_result({"error": "File not found"}, 404)

    file_path = row["path"]

    from .core_impl.audio_extract import has_audio_track
    if not has_audio_track(file_path):
        return _api_result({"error": "File has no audio track"}, 400)

    cfg = _get_config()

    # Override from request body
    body = await request.get_json(silent=True) or {}
    engine = body.get("engine", cfg["engine"])
    model = body.get("model", cfg["model"])
    language = body.get("language", cfg["language"])

    try:
        from .core_impl.transcribe import transcribe_and_save
        result = await asyncio.to_thread(
            transcribe_and_save,
            file_id=file_id,
            file_path=file_path,
            engine=engine,
            model=model,
            language=language,
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        return _api_result(result, 200)

    except RuntimeError as e:
        logger.error("Audio transcription error for file_id=%d: %s", file_id, e)
        return _api_result({"error": "Audio transcription failed"}, 500)
    except Exception:
        logger.exception("Unexpected error in audio transcription for file_id=%d", file_id)
        return _api_result({"error": "Internal audio transcription error"}, 500)


@bp.route("/api/audio-analysis/status")
async def api_status():
    """Check audio analysis availability."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .core_impl.audio_extract import ffmpeg_available
    from .core_impl.whisper_local import is_available as whisper_available

    return _api_result({
        "ffmpeg": ffmpeg_available(),
        "whisper_local": whisper_available(),
        "whisper_api": True,  # Always available if API key is set
    })


def get_blueprint():
    return bp


__all__ = ["get_blueprint"]
