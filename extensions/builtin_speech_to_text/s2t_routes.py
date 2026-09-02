"""Speech-to-Text API routes."""

import contextlib
import json
import logging
import os

from quart import jsonify, request

from core.infra_core.blocking_tasks import run_blocking_sync, run_long_blocking_sync
from core.infra_core.upload_limits import copy_upload_to_temp

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-speech-to-text"
_MAX_AUDIO_UPLOAD_BYTES = 32 * 1024 * 1024


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_s2t_routes(bp):
    """Register S2T API endpoints on the given Blueprint."""

    @bp.route("/api/s2t/transcribe", methods=["POST"])
    async def api_s2t_transcribe():
        """Transcribe uploaded audio (WAV, MP3, OGG, WebM, etc.)."""
        audio_file = (await request.files).get("audio")
        if not audio_file:
            return jsonify({"status": "error", "message": "audio file required"}), 400

        language = (await request.form).get("language") or _get_default_language()
        backend_pref, model_size = _get_config()
        try:
            payload, status = await run_long_blocking_sync(
                _transcribe_upload_sync,
                audio_file,
                language,
                backend_pref,
                model_size,
            )
            return jsonify(payload), status
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 413
        except Exception as exc:
            logger.exception("Transcription failed")
            return jsonify({
                "status": "error",
                "message": f"Transcription failed: {type(exc).__name__}",
            }), 500

    @bp.route("/api/s2t/transcribe-video", methods=["POST"])
    async def api_s2t_transcribe_video():
        """Transcribe audio from a video file by file_id."""
        data = await request.get_json(silent=True) or {}
        file_id = data.get("file_id")
        if not isinstance(file_id, int) or file_id <= 0:
            return jsonify({"status": "error", "message": "file_id required"}), 400

        language = data.get("language") or _get_default_language()
        backend_pref, model_size = _get_config()

        try:
            payload, status = await run_long_blocking_sync(
                _transcribe_video_sync,
                file_id,
                language,
                backend_pref,
                model_size,
            )
            return jsonify(payload), status
        except Exception as exc:
            logger.exception("Video transcription failed")
            return jsonify({
                "status": "error",
                "message": f"Transcription failed: {type(exc).__name__}",
            }), 500

    @bp.route("/api/s2t/transcript/<int:file_id>")
    async def api_s2t_transcript(file_id):
        """Get saved transcript for a file."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        # Import from relocated annotations extension
        from importlib import import_module
        _ann_mod = import_module("extensions.builtin_annotations.core_impl")
        get_annotations_for_file = _ann_mod.get_annotations_for_file

        rows = get_annotations_for_file(file_id, source="s2t")
        if not rows:
            # Fallback: check hailo:s2t source for backward compat
            rows = get_annotations_for_file(file_id, source="hailo:s2t")
        if not rows:
            return jsonify({
                "status": "not_found",
                "message": "No transcript for this file",
            })

        result = {"status": "ok", "file_id": file_id}
        for row in rows:
            if row["key"] == "transcript":
                result["text"] = row["value"]
            elif row["key"] == "transcript_segments":
                try:
                    result["segments"] = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    result["segments"] = []
            elif row["key"] == "transcript_backend":
                result["backend"] = row["value"]
        return jsonify(result)

    @bp.route("/api/s2t/status")
    async def api_s2t_status():
        """Return backend status and available backends."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.backend_registry import (
            detect_available_backends,
            get_active_info,
        )
        def _status_payload():
            return {
                "status": "ok",
                "active": get_active_info(),
                "backends": detect_available_backends(),
            }

        return jsonify(await run_blocking_sync(_status_payload))


def _transcribe_upload_sync(audio_file, language: str, backend_pref: str, model_size: str):
    import wave

    import numpy as np

    tmp_src = None
    tmp_wav = None
    try:
        suffix = _guess_suffix(audio_file.filename)
        tmp_src = copy_upload_to_temp(
            audio_file,
            max_bytes=_MAX_AUDIO_UPLOAD_BYTES,
            suffix=suffix,
            prefix="yu_s2t_src_",
        )

        sample_rate = 16000
        try:
            with wave.open(tmp_src, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
            audio_data = np.frombuffer(raw, dtype=np.int16)
        except wave.Error:
            from core.files_core.video_audio import extract_audio_wav
            tmp_wav = extract_audio_wav(tmp_src, sample_rate=16000)
            if tmp_wav is None:
                return {
                    "status": "error",
                    "message": "Unsupported audio format or ffmpeg not available",
                }, 400

            with wave.open(tmp_wav, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
            audio_data = np.frombuffer(raw, dtype=np.int16)

        from .core_impl.backend_registry import get_backend
        backend = get_backend(backend_pref, model_size)
        segments = backend.transcribe(audio_data, language=language)
        full_text = " ".join(seg["text"] for seg in segments).strip()

        return {
            "status": "ok",
            "text": full_text,
            "segments": segments,
            "language": language,
            "sample_rate": sample_rate,
            "backend": backend.name,
        }, 200
    finally:
        for p in (tmp_src, tmp_wav):
            if p:
                with contextlib.suppress(OSError):
                    os.unlink(p)


def _transcribe_video_sync(file_id: int, language: str, backend_pref: str, model_size: str):
    import wave

    import numpy as np

    from core.services_core.db_api import get_readonly_db
    con = get_readonly_db()
    row = con.execute(
        "SELECT path FROM files WHERE id=? AND is_deleted=0",
        (file_id,),
    ).fetchone()
    if not row:
        return {"status": "error", "message": "File not found"}, 404

    from core.files_core.video_audio import extract_audio_wav
    wav_path = extract_audio_wav(row[0])
    if wav_path is None:
        return {
            "status": "error",
            "message": "Failed to extract audio from video",
        }, 500

    try:
        with wave.open(wav_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        audio_data = np.frombuffer(raw, dtype=np.int16)

        from .core_impl.backend_registry import get_backend
        backend = get_backend(backend_pref, model_size)
        segments = backend.transcribe(audio_data, language=language)
        full_text = " ".join(seg["text"] for seg in segments).strip()

        _save_transcript(file_id, full_text, segments, backend.name)

        return {
            "status": "ok",
            "text": full_text,
            "segments": segments,
            "language": language,
            "backend": backend.name,
        }, 200
    finally:
        with contextlib.suppress(OSError):
            os.unlink(wav_path)


def _save_transcript(file_id: int, text: str, segments: list, backend: str):
    """Save transcript to annotations."""
    # Import from relocated annotations extension
    from importlib import import_module
    _ann_store = import_module("extensions.builtin_annotations.core_impl.store")
    upsert_annotations_batch_commit = _ann_store.upsert_annotations_batch_commit
    upsert_annotations_batch_commit([
        {
            "file_id": file_id,
            "source": "s2t",
            "key": "transcript",
            "value": text,
            "confidence": None,
        },
        {
            "file_id": file_id,
            "source": "s2t",
            "key": "transcript_segments",
            "value": json.dumps(segments, ensure_ascii=False),
            "confidence": None,
        },
        {
            "file_id": file_id,
            "source": "s2t",
            "key": "transcript_backend",
            "value": backend,
            "confidence": None,
        },
    ])


def _get_config() -> tuple:
    """Return (backend_pref, model_size) from extension config."""
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
    backend = get_extension_config_value(_EXT_NAME, "backend", "auto")
    model_size = get_extension_config_value(_EXT_NAME, "model_size", "base")
    return backend, model_size


def _get_default_language() -> str:
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
    return get_extension_config_value(_EXT_NAME, "default_language", "ja")


def _guess_suffix(filename: str | None) -> str:
    """Guess file extension from filename, default to .webm."""
    if filename:
        import os
        _, ext = os.path.splitext(filename)
        if ext:
            return ext.lower()
    return ".webm"
