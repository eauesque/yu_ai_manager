"""Hailo GenAI — VLM image analysis routes."""

import asyncio
import json
import logging
import os

from core.extensions_core.extensions_admin import get_extension_config_value
from quart import Response, jsonify, request

from core.infra_core.upload_limits import read_upload_bytes_limited
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

_EXT_NAME = "builtin-hailo-genai"
logger = logging.getLogger(__name__)
_MAX_IMAGE_UPLOAD_BYTES = 16 * 1024 * 1024


async def _get_param(key: str, default=""):
    """Get a parameter from JSON body or form data."""
    if request.is_json:
        return (await request.get_json()).get(key, default)
    return (await request.form).get(key, default)


def register_vlm_routes(bp):
    """Register VLM routes on the given Blueprint."""

    @bp.route("/api/vlm/generate", methods=["POST"])
    async def api_vlm_generate():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        import cv2
        import numpy as np
        from ext_builtin_hailo_genai.core_impl.model_download import is_hef_available
        from ext_builtin_hailo_genai.core_impl.vlm_inference import get_vlm, preprocess_image

        prompt_text = str(await _get_param("prompt", "")).strip()
        if not prompt_text:
            return jsonify({
                "status": "error", "message": "prompt is required",
            }), 400

        model = str(await _get_param(
            "model",
            get_extension_config_value(_EXT_NAME, "default_vlm_model", "qwen2-vl-2b-instruct"),
        ))
        if not is_hef_available(model):
            return jsonify({
                "status": "error",
                "message": f"Model '{model}' not downloaded yet",
            }), 400

        temperature = float(await _get_param(
            "temperature",
            get_extension_config_value(_EXT_NAME, "temperature", 0.7),
        ))
        max_tokens = int(await _get_param(
            "max_generated_tokens",
            get_extension_config_value(
                _EXT_NAME, "max_generated_tokens", 512,
            ),
        ))

        # Process image: uploaded file or file_id lookup
        frames = []
        image_file = (await request.files).get("image") if not request.is_json else None
        if image_file:
            try:
                file_bytes = np.frombuffer(
                    read_upload_bytes_limited(
                        image_file,
                        max_bytes=_MAX_IMAGE_UPLOAD_BYTES,
                    ),
                    np.uint8,
                )
            except ValueError as exc:
                return jsonify({
                    "status": "error", "message": str(exc),
                }), 413
            image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if image_bgr is not None:
                frames.append(preprocess_image(image_bgr))
        else:
            # JSON body with file_id — resolve path from DB
            file_id = await _get_param("file_id")
            if file_id:
                from core.services_core.db_async import run_db_sync

                def _lookup_path(fid):
                    from core.services_core.db_api import get_readonly_db
                    con = get_readonly_db()
                    return con.execute(
                        "SELECT path FROM files WHERE id=? AND is_deleted=0",
                        (int(fid),),
                    ).fetchone()

                row = await run_db_sync(_lookup_path, file_id)
                if not row:
                    return jsonify({
                        "status": "error",
                        "message": f"file_id {file_id} not found",
                    }), 404
                img_path = row[0]
                if not os.path.isfile(img_path):
                    return jsonify({
                        "status": "error",
                        "message": f"Image file not found on disk: {img_path}",
                    }), 404
                image_bgr = cv2.imread(img_path)
                if image_bgr is not None:
                    frames.append(preprocess_image(image_bgr))

        system_prompt = str(await _get_param(
            "system_prompt",
            "You are a helpful assistant that analyzes images.",
        ))

        # Build prompt with image placeholder if image provided
        user_content = []
        if frames:
            user_content.append({"type": "image"})
        user_content.append({"type": "text", "text": prompt_text})

        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ]

        async def generate_sse():
            try:
                vlm = await asyncio.to_thread(get_vlm, model)
                full_text = []
                it = iter(vlm.generate_stream(
                    messages,
                    frames=frames or None,
                    temperature=temperature,
                    max_generated_tokens=max_tokens,
                ))
                while True:
                    token = await asyncio.to_thread(next, it, None)
                    if token is None:
                        break
                    full_text.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
                yield f"data: {json.dumps({'done': True, 'full_text': ''.join(full_text)})}\n\n"
            except Exception:
                logger.exception("VLM SSE generation failed")
                yield f"data: {json.dumps({'error': 'VLM generation failed'})}\n\n"

        return Response(
            generate_sse(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
