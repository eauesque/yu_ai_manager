"""Hailo GenAI — S2T batch transcription + transcript lookup routes."""

from __future__ import annotations

import contextlib
import json
from typing import TypeVar

from quart import jsonify, request

from core.web.auth_helpers import require_admin_scope as _require_admin_scope

_IN_CHUNK_SIZE = 500
T = TypeVar("T")


def _chunks(items: list[T], size: int | None = None):
    chunk_size = size or _IN_CHUNK_SIZE
    for start in range(0, len(items), chunk_size):
        yield items[start:start + chunk_size]


def _get_active_paths(file_ids: list[int]) -> dict[int, str]:
    """Return active file paths keyed by id."""
    if not file_ids:
        return {}

    from core.services_core.db_api import get_readonly_db

    con = get_readonly_db()
    paths: dict[int, str] = {}
    for chunk in _chunks(file_ids):
        placeholders = ",".join("?" * len(chunk))
        cursor = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted=0",  # noqa: S608
            chunk,
        )
        for row in cursor:
            paths[int(row[0])] = row[1]
    return paths


def register_s2t_batch_routes(bp):
    """Register batch transcription and transcript lookup routes on the Blueprint."""

    @bp.route("/api/s2t/batch-transcribe", methods=["POST"])
    async def api_s2t_batch_transcribe():
        """Start batch video transcription in background."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.model_download import is_hef_available

        data = await request.get_json(silent=True) or {}
        file_ids = data.get("file_ids", [])
        if not file_ids or not isinstance(file_ids, list):
            return jsonify({
                "status": "error", "message": "file_ids is required",
            }), 400

        file_ids = [fid for fid in file_ids if isinstance(fid, int) and fid > 0]
        if not file_ids:
            return jsonify({
                "status": "error", "message": "No valid file_ids",
            }), 400

        model = data.get("model", "whisper-base")
        if not is_hef_available(model):
            return jsonify({
                "status": "error",
                "message": f"Model '{model}' not downloaded yet",
            }), 400

        language = data.get("language", "en")

        # Run in background thread
        import threading

        from core.event_bus import emit

        def _run_batch():
            import os
            import wave

            # Import from relocated extension module
            from importlib import import_module

            import numpy as np
            from ext_builtin_hailo_genai.core_impl.s2t_inference import get_s2t

            from core.files_core.video_audio import extract_audio_wav
            _ann_store = import_module("extensions.builtin_annotations.core_impl.store")
            upsert_annotations_batch_commit = _ann_store.upsert_annotations_batch_commit

            total = len(file_ids)
            emit("video_s2t.start", {"total": total, "model": model},
                 source="video_s2t")

            paths_map = _get_active_paths(file_ids)

            processed = 0
            errors = 0

            try:
                s2t = get_s2t(model)
            except Exception as exc:
                emit("video_s2t.complete", {
                    "reason": f"S2T init failed: {exc}",
                    "processed": 0, "errors": total, "total": total,
                    "elapsed_seconds": 0,
                }, source="video_s2t")
                return

            import time
            started_at = time.time()

            for fid in file_ids:
                video_path = paths_map.get(fid)
                if not video_path:
                    errors += 1
                    continue

                wav_path = extract_audio_wav(video_path)
                if wav_path is None:
                    errors += 1
                    continue

                try:
                    with wave.open(wav_path, "rb") as wf:
                        raw = wf.readframes(wf.getnframes())
                    audio_data = np.frombuffer(raw, dtype=np.int16)

                    segments = s2t.transcribe_segments(audio_data, language=language)
                    full_text = " ".join(seg["text"] for seg in segments).strip()

                    upsert_annotations_batch_commit([
                        {
                            "file_id": fid,
                            "source": "hailo:s2t",
                            "key": "transcript",
                            "value": full_text,
                            "confidence": None,
                        },
                        {
                            "file_id": fid,
                            "source": "hailo:s2t",
                            "key": "transcript_segments",
                            "value": json.dumps(segments),
                            "confidence": None,
                        },
                    ])
                    processed += 1
                except Exception:
                    errors += 1
                finally:
                    with contextlib.suppress(OSError):
                        os.unlink(wav_path)

                elapsed = round(time.time() - started_at, 1)
                pct = round((processed + errors) / total * 100, 1)
                emit("video_s2t.progress", {
                    "processed": processed, "total": total,
                    "errors": errors, "percent": pct,
                    "elapsed": elapsed,
                }, source="video_s2t")

            elapsed = round(time.time() - started_at, 1)
            emit("video_s2t.complete", {
                "reason": "complete",
                "processed": processed, "errors": errors,
                "total": total, "elapsed_seconds": elapsed,
            }, source="video_s2t")

        t = threading.Thread(target=_run_batch, name="video-s2t-batch", daemon=True)
        t.start()
        return jsonify({"status": "started", "total": len(file_ids)})

    @bp.route("/api/s2t/transcript/<int:file_id>")
    async def api_s2t_transcript(file_id):
        """Get saved transcript for a file."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        # Import from relocated extension module
        from importlib import import_module
        _ann_mod = import_module("extensions.builtin_annotations.core_impl")
        get_annotations_for_file = _ann_mod.get_annotations_for_file

        rows = get_annotations_for_file(file_id, source="hailo:s2t")
        if not rows:
            return jsonify({
                "status": "not_found",
                "message": "No transcript found for this file",
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
        return jsonify(result)
