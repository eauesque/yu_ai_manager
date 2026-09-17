"""Hailo GenAI — Chat helper functions (request parsing, image prep, streaming)."""

import asyncio
import json
import logging

from quart import Response, request

from core.infra_core.upload_limits import read_upload_bytes_limited

logger = logging.getLogger(__name__)

_MAX_IMAGE_UPLOAD_BYTES = 16 * 1024 * 1024

async def parse_send_request():
    """Extract parameters from JSON or multipart/form-data request."""
    if request.content_type and "multipart" in request.content_type:
        data = {}
        for key in ("content", "model", "conversation_id", "temperature",
                     "max_tokens", "system_prompt", "extra_context",
                     "file_id"):
            val = (await request.form).get(key)
            if val is not None:
                data[key] = val
        data["web_search"] = (await request.form).get("web_search", "").lower() in (
            "true", "1", "yes",
        )
        img = (await request.files).get("image")
        if img and img.filename:
            data["_image_file"] = img
        return data
    data = await request.get_json(silent=True) or {}
    return data


def prepare_image(image_file, file_id):
    """Preprocess image for VLM inference. Returns (frames, error)."""
    import numpy as np

    try:
        import cv2
    except ImportError:
        return None, "OpenCV (cv2) is not installed"

    from ext_builtin_hailo_genai.core_impl.vlm_inference import preprocess_image

    img = None
    if image_file:
        # Decode from uploaded file
        try:
            raw = read_upload_bytes_limited(
                image_file,
                max_bytes=_MAX_IMAGE_UPLOAD_BYTES,
            )
        except ValueError as exc:
            return None, str(exc)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    elif file_id:
        # Resolve path from DB file ID
        try:
            from core.services_core.db_connection import get_readonly_db
            db = get_readonly_db()
            row = db.execute(
                "SELECT path FROM files WHERE id=? AND is_deleted=0",
                (int(file_id),),
            ).fetchone()
            if row:
                img = cv2.imread(row[0])
        except Exception:
            logger.debug("image lookup failed for %s", file_id, exc_info=True)

    if img is None:
        return None, "Could not read image"

    frame = preprocess_image(img)
    return [frame], None


def stream_vlm_response(
    conv_id, prompt_text, frames, temperature,
    max_tokens, new_title, search_results, add_message,
    vlm_model="qwen2-vl-2b-instruct",
):
    """Return VLM streaming response as SSE.

    ``vlm_model`` selects which VLM HEF to load (e.g. ``qwen2-vl-2b-instruct``
    or ``qwen3-vl-2b-instruct``). Callers should resolve the configured
    default before invoking this helper.
    """

    async def generate_sse():
        try:
            from ext_builtin_hailo_genai.core_impl.llm_control import async_close_llm

            from core.configuration.api import load_config_json
            _cfg = load_config_json(None)
            # Free the LLM (subprocess mode → ControlMessage; otherwise direct).
            await async_close_llm(_cfg)

            from ext_builtin_hailo_genai.core_impl.vlm_inference import close_vlm, get_vlm
            vlm = await asyncio.to_thread(get_vlm, vlm_model)
            full_text = []

            init_data = {
                'conversation_id': conv_id,
                'title': new_title,
                'vlm': True,
            }
            if search_results:
                init_data['search_results'] = search_results
            yield f"data: {json.dumps(init_data)}\n\n"

            it = iter(vlm.generate_stream(
                prompt_text,
                frames=frames,
                temperature=temperature,
                max_generated_tokens=max_tokens,
            ))
            while True:
                token = await asyncio.to_thread(next, it, None)
                if token is None:
                    break
                full_text.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"

            assistant_text = "".join(full_text)
            await asyncio.to_thread(add_message, conv_id, "assistant", assistant_text)

            yield f"data: {json.dumps({'done': True, 'full_text': assistant_text, 'conversation_id': conv_id})}\n\n"

            await asyncio.to_thread(close_vlm)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("VLM SSE error: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(
        generate_sse(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def clear_llm_context():
    """Clear LLM context if loaded (sync wrapper, used by legacy callsites)."""
    try:
        from ext_builtin_hailo_genai.core_impl.llm_inference import _instance, use_subprocess

        from core.configuration.api import load_config_json
        _cfg = load_config_json(None)
        if use_subprocess(_cfg):
            # async RPC required for subprocess mode — schedule on event loop
            # or run via asyncio if needed. We expose async_clear_llm_context
            # for async callers; this sync wrapper is best-effort no-op when
            # in subprocess mode because there's no running event loop here.
            import asyncio

            from ext_builtin_hailo_genai.core_impl.llm_control import (
                async_clear_llm_context,
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Caller should use the async variant in this case.
                    return
                loop.run_until_complete(async_clear_llm_context(_cfg))
            except Exception:
                logger.debug("context clear failed", exc_info=True)
        elif _instance is not None:
            _instance.clear_context()
    except Exception:
        logger.debug("chat helper step failed", exc_info=True)
