"""Hailo GenAI — LLM generation + context management routes."""

import asyncio
import json
import logging

from core.extensions_core.extensions_admin import get_extension_config_value
from openai_helpers import _validate_generation_request_types
from quart import Response, jsonify, request

from core.infra_core.blocking_tasks import run_long_blocking_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

_EXT_NAME = "builtin-hailo-genai"
logger = logging.getLogger(__name__)


def register_llm_routes(bp):
    """Register LLM routes on the given Blueprint."""

    @bp.route("/api/llm/generate", methods=["POST"])
    async def api_llm_generate():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        data = await request.get_json(silent=True) or {}
        if err := _validate_generation_request_types(data, max_tokens_field="max_generated_tokens"):
            return jsonify({"status": "error", "message": err}), 400

        from ext_builtin_hailo_genai.core_impl.model_download import is_hef_available

        # Multi-turn support: accept messages array or single prompt
        messages = data.get("messages")
        if messages and isinstance(messages, list):
            if not all(isinstance(m, dict) and "role" in m for m in messages):
                return jsonify({
                    "status": "error",
                    "message": "Invalid messages format",
                }), 400
        else:
            prompt_text = data.get("prompt", "").strip()
            if not prompt_text:
                return jsonify({
                    "status": "error", "message": "prompt or messages is required",
                }), 400
            system_prompt = data.get("system_prompt", "You are a helpful assistant.")
            messages = [
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "text", "text": prompt_text}]},
            ]

        model = data.get(
            "model",
            get_extension_config_value(
                _EXT_NAME, "default_llm_model", "qwen3-1.7b-instruct",
            ),
        )
        if not is_hef_available(model):
            return jsonify({
                "status": "error",
                "message": f"Model '{model}' not downloaded yet",
            }), 400

        temperature = float(data.get(
            "temperature",
            get_extension_config_value(_EXT_NAME, "temperature", 0.7),
        ))
        max_tokens = int(data.get(
            "max_generated_tokens",
            get_extension_config_value(
                _EXT_NAME, "max_generated_tokens", 512,
            ),
        ))

        async def generate_sse():
            from ext_builtin_hailo_genai.core_impl.llm_inference import (
                HailoBusyError,
                HailoLLMSubprocessClient,
                stream_with_keepalive,
                use_subprocess,
            )

            from core.configuration.api import load_config_json

            config = load_config_json(None)
            try:
                full_text: list[str] = []
                if use_subprocess(config):
                    import uuid

                    from core.inference_worker.bridge import inference_bridge

                    client = HailoLLMSubprocessClient(inference_bridge, uuid.uuid4().hex, model)
                    try:
                        stream = client.stream(
                            messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        async for kind, tok in stream_with_keepalive(stream):
                            if kind == "ping":
                                yield f"data: {json.dumps({'keepalive': True})}\n\n"
                                continue
                            if isinstance(tok, str):
                                full_text.append(tok)
                                yield f"data: {json.dumps({'token': tok})}\n\n"
                            else:
                                yield f"data: {json.dumps({'error': tok.error or 'stream_error'})}\n\n"
                                return
                    except HailoBusyError:
                        # See chat route comment — surface in event body.
                        yield f"data: {json.dumps({'error': 'hailo_npu_busy', 'retry_after': 30})}\n\n"
                        return
                else:
                    from ext_builtin_hailo_genai.core_impl.llm_inference import get_llm
                    llm = await run_long_blocking_sync(get_llm, model)
                    it = iter(llm.generate_stream(
                        messages,
                        temperature=temperature,
                        max_generated_tokens=max_tokens,
                    ))
                    while True:
                        # Token iteration is per-token streaming work; keep it off the event loop.
                        token = await asyncio.to_thread(next, it, None)
                        if token is None:
                            break
                        full_text.append(token)
                        yield f"data: {json.dumps({'token': token})}\n\n"
                yield f"data: {json.dumps({'done': True, 'full_text': ''.join(full_text)})}\n\n"
            except Exception:
                logger.exception("LLM SSE generation failed")
                yield f"data: {json.dumps({'error': 'LLM generation failed'})}\n\n"

        resp = Response(
            generate_sse(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
        resp.timeout = None  # disable Quart RESPONSE_TIMEOUT (60s default) for SSE
        return resp

    @bp.route("/api/llm/clear-context", methods=["POST"])
    async def api_llm_clear_context():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.llm_control import (
            async_clear_llm_context,
            async_is_model_active,
        )
        from ext_builtin_hailo_genai.core_impl.llm_inference import _instance

        from core.configuration.api import load_config_json

        config = load_config_json(None)
        if not (await async_is_model_active("llm", config) or _instance is not None):
            return jsonify({
                "status": "error", "message": "No LLM loaded",
            }), 400
        try:
            await async_clear_llm_context(config)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        return jsonify({"status": "ok"})
