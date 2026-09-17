"""Hailo GenAI — Speech2Text routes (single-file transcription + video).

Split into:
  - hailo_s2t_routes.py (single transcribe + video transcribe — this file)
  - hailo_s2t_batch.py  (batch transcription + transcript lookup)
"""

import asyncio
import contextlib
import json
import os

from hailo_s2t_batch import register_s2t_batch_routes
from openai_helpers import _convert_path_to_wav
from quart import jsonify, request

from core.infra_core.upload_limits import copy_upload_to_temp
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

_MAX_AUDIO_UPLOAD_BYTES = 32 * 1024 * 1024


def register_s2t_routes(bp):
    """Register S2T routes on the given Blueprint."""

    # Register batch + transcript lookup routes from split module
    register_s2t_batch_routes(bp)

    @bp.route("/api/s2t/transcribe", methods=["POST"])
    async def api_s2t_transcribe():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        import wave

        import numpy as np
        from ext_builtin_hailo_genai.core_impl.model_download import is_hef_available
        from ext_builtin_hailo_genai.core_impl.s2t_inference import get_s2t

        audio_file = (await request.files).get("audio")
        if not audio_file:
            return jsonify({
                "status": "error", "message": "audio file is required",
            }), 400

        model = (await request.form).get("model", "whisper-base")
        if not is_hef_available(model):
            return jsonify({
                "status": "error",
                "message": f"Model '{model}' not downloaded yet",
            }), 400

        language = (await request.form).get("language", "en")

        try:
            filename = audio_file.filename or "audio.wav"
            suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".bin"
            src_path = copy_upload_to_temp(
                audio_file,
                max_bytes=_MAX_AUDIO_UPLOAD_BYTES,
                suffix=suffix,
                prefix="yu_hailo_s2t_",
            )
            wav_path = src_path
            if not filename.lower().endswith(".wav"):
                wav_path = await asyncio.to_thread(_convert_path_to_wav, src_path)
            with wave.open(wav_path, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()

            audio_data = np.frombuffer(raw, dtype=np.int16)

            def _transcribe():
                s2t = get_s2t(model)
                return s2t.transcribe_segments(audio_data, language=language)

            segments = await asyncio.to_thread(_transcribe)
            full_text = " ".join(seg["text"] for seg in segments).strip()

            return jsonify({
                "status": "ok",
                "text": full_text,
                "segments": segments,
                "language": language,
                "sample_rate": sample_rate,
            })
        except ValueError as exc:
            return jsonify({
                "status": "error",
                "message": str(exc),
            }), 413
        except Exception as exc:
            return jsonify({
                "status": "error",
                "message": f"Transcription failed: {type(exc).__name__}: {exc}",
            }), 500
        finally:
            for p in locals().get("src_path"), locals().get("wav_path"):
                if p:
                    with contextlib.suppress(OSError):
                        os.unlink(p)

    @bp.route("/api/s2t/transcribe-video", methods=["POST"])
    async def api_s2t_transcribe_video():
        """Transcribe a single video file by file_id."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        import os
        import wave

        import numpy as np
        from ext_builtin_hailo_genai.core_impl.model_download import is_hef_available
        from ext_builtin_hailo_genai.core_impl.s2t_inference import get_s2t

        from core.files_core.video_audio import extract_audio_wav

        data = await request.get_json(silent=True) or {}
        file_id = data.get("file_id")
        if not isinstance(file_id, int) or file_id <= 0:
            return jsonify({
                "status": "error", "message": "file_id is required",
            }), 400

        model = data.get("model", "whisper-base")
        if not is_hef_available(model):
            return jsonify({
                "status": "error",
                "message": f"Model '{model}' not downloaded yet",
            }), 400

        language = data.get("language", "en")

        # Get file path from DB
        from core.services_core.db_async import run_db_sync

        def _lookup_video(fid):
            from core.services_core.db_api import get_readonly_db
            con = get_readonly_db()
            return con.execute(
                "SELECT path FROM files WHERE id=? AND is_deleted=0",
                (fid,),
            ).fetchone()

        row = await run_db_sync(_lookup_video, file_id)

        if not row:
            return jsonify({
                "status": "error", "message": "File not found",
            }), 404

        video_path = row[0]

        # Extract audio + transcribe in thread
        def _extract_and_transcribe():
            wav_path = extract_audio_wav(video_path)
            if wav_path is None:
                return None, None, "Failed to extract audio from video"
            try:
                with wave.open(wav_path, "rb") as wf:
                    raw_audio = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(raw_audio, dtype=np.int16)
                s2t = get_s2t(model)
                segments = s2t.transcribe_segments(audio_data, language=language)
                full_text = " ".join(seg["text"] for seg in segments).strip()
                return full_text, segments, None
            except Exception as exc:
                return None, None, f"Transcription failed: {type(exc).__name__}: {exc}"
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(wav_path)

        full_text, segments, err = await asyncio.to_thread(_extract_and_transcribe)

        if err:
            return jsonify({"status": "error", "message": err}), 500

        # Save to annotations
        def _save_annotations():
            # Import from relocated extension module
            from importlib import import_module
            _ann_store = import_module("extensions.builtin_annotations.core_impl.store")
            upsert_annotations_batch_commit = _ann_store.upsert_annotations_batch_commit
            upsert_annotations_batch_commit([
                {
                    "file_id": file_id,
                    "source": "hailo:s2t",
                    "key": "transcript",
                    "value": full_text,
                    "confidence": None,
                },
                {
                    "file_id": file_id,
                    "source": "hailo:s2t",
                    "key": "transcript_segments",
                    "value": json.dumps(segments),
                    "confidence": None,
                },
            ])

        await run_db_sync(_save_annotations)

        return jsonify({
            "status": "ok",
            "text": full_text,
            "segments": segments,
            "language": language,
        })
