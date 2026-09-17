"""Streaming and non-streaming completion helpers."""

from __future__ import annotations

import asyncio
import logging

from openai_helpers import _completion_id, _openai_error, _sse_chunk, _ts
from quart import Response, jsonify

logger = logging.getLogger(__name__)


async def llm_completion(model, hailo_messages, temperature, max_tokens, stream, model_display):
    from ext_builtin_hailo_genai.core_impl.llm_inference import (
        HailoBusyError,
        HailoLLMSubprocessClient,
        get_llm,
        stream_with_keepalive,
        use_subprocess,
    )

    from core.configuration.api import load_config_json

    config = load_config_json(None)
    cid = _completion_id()
    ts = _ts()
    subprocess_mode = use_subprocess(config)

    if not stream:
        try:
            if subprocess_mode:
                import uuid

                from core.inference_worker.bridge import inference_bridge

                client = HailoLLMSubprocessClient(inference_bridge, uuid.uuid4().hex, model)
                try:
                    text = await client.generate_all(
                        hailo_messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                except HailoBusyError as exc:
                    return _openai_error(
                        str(exc),
                        type_="server_error",
                        code="device_busy",
                        status=503,
                    )
            else:
                llm = await asyncio.to_thread(get_llm, model)
                text = await asyncio.to_thread(
                    llm.generate_all,
                    hailo_messages,
                    temperature=temperature,
                    max_generated_tokens=max_tokens,
                )
            return jsonify(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": ts,
                    "model": model_display,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }
            )
        except Exception as exc:
            return _openai_error(
                str(exc),
                type_="server_error",
                code="device_busy" if "busy" in str(exc).lower() else None,
                status=503 if "busy" in str(exc).lower() else 500,
            )

    async def sse_stream():
        try:
            yield _sse_chunk(cid, ts, model_display, role="assistant")
            if subprocess_mode:
                import uuid

                from core.inference_worker.bridge import inference_bridge

                client = HailoLLMSubprocessClient(inference_bridge, uuid.uuid4().hex, model)
                try:
                    stream = client.stream(
                        hailo_messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    async for kind, tok in stream_with_keepalive(stream):
                        if kind == "ping":
                            # OpenAI-compatible clients tolerate SSE comments
                            yield ": keepalive\n\n"
                            continue
                        if isinstance(tok, str):
                            yield _sse_chunk(cid, ts, model_display, content=tok)
                        else:
                            break
                except HailoBusyError:
                    import json
                    error_payload = json.dumps({"error": "hailo_npu_busy", "retry_after": 30})
                    yield f"event: error\ndata: {error_payload}\n\n"
                    return
            else:
                llm = await asyncio.to_thread(get_llm, model)
                it = iter(
                    llm.generate_stream(
                        hailo_messages,
                        temperature=temperature,
                        max_generated_tokens=max_tokens,
                    )
                )
                while True:
                    token = await asyncio.to_thread(next, it, None)
                    if token is None:
                        break
                    yield _sse_chunk(cid, ts, model_display, content=token)
            yield _sse_chunk(cid, ts, model_display, finish_reason="stop")
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("LLM streaming error: %s", exc)
            yield _sse_chunk(cid, ts, model_display, finish_reason="error")
            yield "data: [DONE]\n\n"

    resp = Response(
        sse_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    resp.timeout = None  # disable Quart RESPONSE_TIMEOUT (60s default) for SSE
    return resp


async def vlm_completion(vlm_model, user_text, image_bgr, temperature, max_tokens, stream, model_display):
    from ext_builtin_hailo_genai.core_impl.vlm_inference import get_vlm, preprocess_image

    cid = _completion_id()
    ts = _ts()
    frame = preprocess_image(image_bgr)

    if not stream:
        try:
            vlm = await asyncio.to_thread(get_vlm, vlm_model)
            text = await asyncio.to_thread(
                vlm.generate_all,
                user_text,
                [frame],
                temperature=temperature,
                max_generated_tokens=max_tokens,
            )
            return jsonify(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": ts,
                    "model": model_display,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }
            )
        except Exception as exc:
            return _openai_error(
                str(exc),
                type_="server_error",
                code="device_busy" if "busy" in str(exc).lower() else None,
                status=503 if "busy" in str(exc).lower() else 500,
            )

    async def sse_stream():
        try:
            vlm = await asyncio.to_thread(get_vlm, vlm_model)
            yield _sse_chunk(cid, ts, model_display, role="assistant")
            it = iter(
                vlm.generate_stream(
                    user_text,
                    [frame],
                    temperature=temperature,
                    max_generated_tokens=max_tokens,
                )
            )
            while True:
                token = await asyncio.to_thread(next, it, None)
                if token is None:
                    break
                yield _sse_chunk(cid, ts, model_display, content=token)
            yield _sse_chunk(cid, ts, model_display, finish_reason="stop")
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("VLM streaming error: %s", exc)
            yield _sse_chunk(cid, ts, model_display, finish_reason="error")
            yield "data: [DONE]\n\n"

    resp = Response(
        sse_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    resp.timeout = None  # disable Quart RESPONSE_TIMEOUT (60s default) for SSE
    return resp
