"""OpenAI-compatible audio transcription and embedding routes.

Handles ``/v1/audio/transcriptions`` and ``/v1/embeddings`` endpoints.
"""

import asyncio
import logging
import wave

import numpy as np
from openai_helpers import (
    _convert_path_to_wav,
    _openai_error,
    _resolve_model,
)
from quart import Response, jsonify, request

from core.infra_core.upload_limits import copy_upload_to_temp
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

logger = logging.getLogger(__name__)
_MAX_AUDIO_UPLOAD_BYTES = 32 * 1024 * 1024


def register_openai_media_routes(bp):
    """Register /v1/audio/transcriptions and /v1/embeddings on the Blueprint."""

    # ── POST /v1/audio/transcriptions ────────────────────────────

    @bp.route("/v1/audio/transcriptions", methods=["POST"])
    async def openai_audio_transcriptions():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.model_download import GENAI_MODELS, is_hef_available
        files = await request.files
        audio_file = files.get("file")
        if not audio_file:
            return _openai_error("file is required")

        form = await request.form
        model_raw = form.get("model", "whisper-1")
        model = _resolve_model(model_raw)
        language = form.get("language", "en")
        response_format = form.get("response_format", "json")

        if model not in GENAI_MODELS:
            return _openai_error(
                f"Model '{model}' not found",
                code="model_not_found", status=404,
            )
        if not is_hef_available(model):
            return _openai_error(
                f"Model '{model}' not downloaded",
                code="model_not_found", status=404,
            )

        try:
            filename = audio_file.filename or "audio.wav"
            suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".bin"
            src_path = copy_upload_to_temp(
                audio_file,
                max_bytes=_MAX_AUDIO_UPLOAD_BYTES,
                suffix=suffix,
                prefix="yu_openai_audio_",
            )
            wav_path = src_path

            # Non-WAV: convert via ffmpeg
            if not filename.lower().endswith(".wav"):
                try:
                    wav_path = await asyncio.to_thread(
                        _convert_path_to_wav, src_path,
                    )
                except Exception as exc:
                    return _openai_error(
                        f"Audio conversion failed: {exc}. "
                        "Install ffmpeg or upload WAV format.",
                        status=400,
                    )

            with wave.open(wav_path, "rb") as wf:
                raw = wf.readframes(wf.getnframes())

            audio_data = np.frombuffer(raw, dtype=np.int16)

            from ext_builtin_hailo_genai.core_impl.s2t_inference import get_s2t
            s2t = await asyncio.to_thread(get_s2t, model)
            segments = await asyncio.to_thread(
                s2t.transcribe_segments, audio_data, language=language,
            )
            full_text = " ".join(seg["text"] for seg in segments).strip()

            if response_format == "text":
                return Response(full_text, mimetype="text/plain")

            if response_format == "verbose_json":
                duration = segments[-1]["end"] if segments else 0.0
                return jsonify({
                    "task": "transcribe",
                    "language": language,
                    "duration": duration,
                    "text": full_text,
                    "segments": [
                        {
                            "id": i,
                            "start": seg["start"],
                            "end": seg["end"],
                            "text": seg["text"],
                        }
                        for i, seg in enumerate(segments)
                    ],
                })

            # Default: json
            return jsonify({"text": full_text})

        except ValueError as exc:
            return _openai_error(str(exc), status=413)
        except Exception as exc:
            return _openai_error(
                f"Transcription failed: {type(exc).__name__}: {exc}",
                type_="server_error", status=500,
            )
        finally:
            for p in locals().get("src_path"), locals().get("wav_path"):
                if p:
                    try:
                        import os
                        os.unlink(p)
                    except OSError:
                        pass

    # ── POST /v1/embeddings ──────────────────────────────────────

    @bp.route("/v1/embeddings", methods=["POST"])
    async def openai_embeddings():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}

        model_raw = data.get("model", "clip-vit-b-16")
        input_data = data.get("input")

        if input_data is None:
            return _openai_error("input is required")

        # Normalise to list
        if isinstance(input_data, str):
            inputs = [input_data]
        elif isinstance(input_data, list):
            inputs = input_data
        else:
            return _openai_error("input must be a string or array of strings")

        if not inputs:
            return _openai_error("input must not be empty")

        try:
            from core.clip_core.text_encoder import encode_text

            embeddings = []
            for i, text in enumerate(inputs):
                if not isinstance(text, str):
                    return _openai_error(
                        f"input[{i}] must be a string",
                    )
                vec = await asyncio.to_thread(encode_text, text)
                embeddings.append({
                    "object": "embedding",
                    "index": i,
                    "embedding": vec.tolist(),
                })

            return jsonify({
                "object": "list",
                "data": embeddings,
                "model": model_raw,
                "usage": {
                    "prompt_tokens": 0,
                    "total_tokens": 0,
                },
            })
        except ImportError:
            return _openai_error(
                "CLIP text encoder not available. "
                "Enable the builtin-clip-search extension.",
                type_="server_error", status=503,
            )
        except Exception as exc:
            return _openai_error(
                f"Embedding failed: {type(exc).__name__}: {exc}",
                type_="server_error", status=500,
            )
