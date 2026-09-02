"""REST endpoints for inference offloading between peers.

Provides health check (public) and inference endpoints for
CLIP encoding, YOLO detection, WD-Tagger tagging, and Whisper S2T.

All CPU-bound inference runs in a thread pool executor to avoid
blocking the Quart async event loop.
"""
from __future__ import annotations

import asyncio
import base64
import functools
import logging

from PIL import UnidentifiedImageError
from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import PeerLlmChatRequest

logger = logging.getLogger(__name__)
_AUTH_PREFIX = "/ext/lan_cowork"


def _run_sync(fn, *args):
    """Run a synchronous function in the default thread pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, functools.partial(fn, *args))


def _is_image_decode_error(exc: Exception) -> bool:
    if isinstance(exc, UnidentifiedImageError):
        return True
    return isinstance(exc, ValueError) and str(exc) == "Failed to decode image"


def register_routes(bp: Blueprint, get_manager) -> None:
    from ..core_impl.peer_auth import require_peer_auth

    _auth = require_peer_auth(get_manager)

    @auth_route(bp, "/api/peer/infer/health", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def infer_health():
        """Return inference capabilities for an authenticated peer."""
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

        inf_state = getattr(mgr, "inference_state", None)
        caps = getattr(mgr, "inference_capabilities", [])

        inference_types = inf_state.get_inference_types() if inf_state else []
        capabilities = [c.to_dict() for c in caps]

        return jsonify({
            "ok": True,
            "inference_types": inference_types,
            "capabilities": capabilities,
        })

    @auth_route(bp, "/api/peer/infer/clip-encode", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def infer_clip_encode():
        """CLIP-encode images and return base64 vectors."""
        mgr = get_manager()
        inf_state = getattr(mgr, "inference_state", None)
        if inf_state is None:
            return jsonify({"ok": False, "error": "inference not available"}), 503

        from ..core_impl.inference.clip import (
            clip_encode_single,
            get_clip_encoder,
            preprocess_clip_image,
        )

        encoder = inf_state.get_clip_encoder()
        if encoder is None:
            encoder = await _run_sync(get_clip_encoder, inf_state)
        if encoder is None:
            return jsonify({"ok": False, "error": "CLIP encoder unavailable"}), 503

        body = await request.get_data()
        content_type = request.content_type or ""

        from ..core_impl.inference.preprocess import extract_multipart_images

        images = extract_multipart_images(body, content_type)
        if not images:
            return jsonify({"ok": False, "error": "no images in request"}), 400

        backend = inf_state.get_clip_backend()

        def _encode_all():
            vectors = []
            for img_data in images:
                preprocessed = preprocess_clip_image(img_data, backend)
                vec = clip_encode_single(encoder, preprocessed, backend)
                vectors.append(base64.b64encode(vec.tobytes()).decode("ascii"))
            return vectors

        try:
            vectors = await _run_sync(_encode_all)
        except (UnidentifiedImageError, ValueError) as exc:
            if not _is_image_decode_error(exc):
                raise
            logger.warning("clip-encode: image decode failed: %s", exc)
            return jsonify({"ok": False, "error": "invalid image data"}), 400
        return jsonify({"ok": True, "vectors": vectors, "model": "clip_vit_b_16", "count": len(vectors)})

    @auth_route(bp, "/api/peer/infer/yolo-detect", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def infer_yolo_detect():
        """Run YOLO object detection on uploaded images."""
        mgr = get_manager()
        inf_state = getattr(mgr, "inference_state", None)
        if inf_state is None:
            return jsonify({"ok": False, "error": "inference not available"}), 503

        from ..core_impl.inference.yolo import (
            preprocess_yolo_image,
            yolo_detect_single,
        )

        # Engine is preloaded at startup — no lazy init here
        engine = inf_state.get_yolo_engine()
        if engine is None:
            return jsonify({"ok": False, "error": "YOLO engine unavailable"}), 503

        body = await request.get_data()
        content_type = request.content_type or ""

        from ..core_impl.inference.preprocess import extract_multipart_images

        images = extract_multipart_images(body, content_type)
        if not images:
            return jsonify({"ok": False, "error": "no images in request"}), 400

        input_size = engine.get("input_size", 640)

        def _detect_all():
            results = []
            for img_data in images:
                image_rgb, scale_info = preprocess_yolo_image(img_data, input_size)
                detections = yolo_detect_single(engine, image_rgb, scale_info)
                results.append(detections)
            return results

        try:
            results = await _run_sync(_detect_all)
        except (UnidentifiedImageError, ValueError) as exc:
            if not _is_image_decode_error(exc):
                raise
            logger.warning("yolo-detect: image decode failed: %s", exc)
            return jsonify({"ok": False, "error": "invalid image data"}), 400
        model_name = engine.get("model_name", "unknown")
        return jsonify({"ok": True, "detections": results, "model": model_name, "count": len(results)})

    @auth_route(bp, "/api/peer/infer/tag", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def infer_tag():
        """Run WD-Tagger inference on a single image."""
        mgr = get_manager()
        inf_state = getattr(mgr, "inference_state", None)
        if inf_state is None:
            return jsonify({"ok": False, "error": "inference not available"}), 503

        engine = inf_state.get_tagger_engine()
        if engine is None:
            return jsonify({"ok": False, "error": "tagger engine unavailable"}), 503

        body = await request.get_data()
        content_type = request.content_type or ""

        from ..core_impl.inference.preprocess import extract_multipart_image

        image_data = extract_multipart_image(body, content_type)
        if image_data is None:
            return jsonify({"ok": False, "error": "no image in request"}), 400

        try:
            tags = await _run_sync(engine.predict, image_data)
        except (UnidentifiedImageError, ValueError) as exc:
            if not _is_image_decode_error(exc):
                raise
            logger.warning("tag: image decode failed: %s", exc)
            return jsonify({"ok": False, "error": "invalid image data"}), 400
        return jsonify({"ok": True, "tags": tags, "model": inf_state.get_model_name()})

    @auth_route(bp, "/api/peer/infer/whisper-transcribe", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def infer_whisper_transcribe():
        """Transcribe audio bytes (WAV octet-stream) using the local Whisper backend.

        Query params:
          language (str): BCP-47 language code hint, e.g. "ja", "en" (default "en")

        Request body: raw WAV bytes (Content-Type: application/octet-stream)

        Response: {"ok": true, "text": "...", "segments": [{text, start, end}, ...]}
        """
        import io
        import wave

        import numpy as np

        mgr = get_manager()
        inf_state = getattr(mgr, "inference_state", None)
        if inf_state is None:
            return jsonify({"ok": False, "error": "inference not available"}), 503

        backend = inf_state.get_whisper_backend()
        if backend is None:
            return jsonify({"ok": False, "error": "Whisper backend unavailable"}), 503

        language = request.args.get("language", "en")

        raw = await request.get_data()
        if not raw:
            return jsonify({"ok": False, "error": "empty request body"}), 400

        def _load_wav(data: bytes) -> np.ndarray:
            with wave.open(io.BytesIO(data)) as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                n_frames = wf.getnframes()
                raw_frames = wf.readframes(n_frames)
            if sampwidth == 2:
                audio = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                audio = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                audio = np.frombuffer(raw_frames, dtype=np.float32)
            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)
            return audio

        try:
            audio_data = await _run_sync(_load_wav, raw)
        except Exception as exc:
            logger.warning("whisper-transcribe: WAV parse failed: %s", exc)
            return jsonify({"ok": False, "error": "invalid WAV data"}), 400

        try:
            segments = await _run_sync(backend.transcribe, audio_data, language)
        except Exception as exc:
            logger.warning("whisper-transcribe: inference failed: %s", exc)
            return jsonify({"ok": False, "error": "transcription failed"}), 502

        full_text = " ".join(s.get("text", "") for s in segments).strip()
        return jsonify({
            "ok": True,
            "text": full_text,
            "segments": segments,
            "model": getattr(backend, "name", "whisper"),
        })

    @auth_route(bp, "/api/peer/infer/llm-chat", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def infer_llm_chat():
        """Run LLM chat inference using the configured LLM client."""
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

        llm_client = mgr.inference_state.get_llm_client()
        if llm_client is None:
            return jsonify({"ok": False, "error": "no LLM client configured"}), 503

        data, err = await require_json_model(request, PeerLlmChatRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        messages = data.messages
        max_tokens = data.max_tokens
        temperature = float(data.temperature)

        try:
            resp = await llm_client.chat(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return jsonify({
                "ok": True,
                "message": {"role": "assistant", "content": resp.content},
                "model": resp.model,
                "usage": resp.usage,
            })
        except Exception as exc:
            logger.warning("LLM chat failed: %s", exc)
            return jsonify({"ok": False, "error": "LLM inference failed"}), 502
