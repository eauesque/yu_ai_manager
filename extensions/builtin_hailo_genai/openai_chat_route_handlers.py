"""Blueprint route registration for OpenAI-compatible chat routes."""

from __future__ import annotations

from core.extensions_core.extensions_admin import get_extension_config_value
from openai_helpers import (
    _EMBEDDING_MODEL_ID,
    _extract_images,
    _extract_text_messages,
    _has_images,
    _messages_to_hailo_format,
    _openai_error,
    _resolve_model,
    _ts,
    _validate_chat_request_types,
)
from quart import jsonify, request

from core.web.auth_helpers import require_admin_scope as _require_admin_scope

try:
    from .openai_chat_stream import llm_completion, vlm_completion
except ImportError:  # pragma: no cover - top-level extension import path
    from openai_chat_stream import llm_completion, vlm_completion

EXT_NAME = "builtin-hailo-genai"


def register_openai_chat_route_handlers(bp):
    @bp.route("/v1")
    @bp.route("/v1/")
    async def openai_v1_info():
        return jsonify({"object": "info", "version": "1", "provider": "hailo"})

    @bp.route("/v1/models")
    async def openai_models():
        from ext_builtin_hailo_genai.core_impl.model_download import GENAI_MODELS, is_hef_available

        ts = _ts()
        data = []
        for name, _info in GENAI_MODELS.items():
            if not is_hef_available(name):
                continue
            data.append({"id": name, "object": "model", "created": ts, "owned_by": "hailo", "permission": []})

        try:
            from core.clip_core.text_encoder import encode_text  # noqa: F401

            data.append({"id": _EMBEDDING_MODEL_ID, "object": "model", "created": ts, "owned_by": "hailo", "permission": []})
        except ImportError:
            pass
        return jsonify({"object": "list", "data": data})

    @bp.route("/v1/chat/completions", methods=["POST"])
    async def openai_chat_completions():
        # Admin scope applies to both API-key and trusted-peer callers.
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        if err := _validate_chat_request_types(data, require_messages=True):
            return _openai_error(err)
        messages = data.get("messages")

        from ext_builtin_hailo_genai.core_impl.genai_types import GenAIModelType
        from ext_builtin_hailo_genai.core_impl.model_download import GENAI_MODELS, is_hef_available

        # Read the configured default from extension config so environments that
        # still have qwen2.5-1.5b-chat (or another model) downloaded keep working
        # when clients omit `model`. Falling back to the hardcoded literal here
        # caused model_not_found regressions on upgraded installs.
        default_llm = get_extension_config_value(EXT_NAME, "default_llm_model", "qwen3-1.7b-instruct")
        model_raw = data.get("model", default_llm)
        model = _resolve_model(model_raw)
        stream = data.get("stream", False)
        temperature = float(data.get("temperature", 0.7))
        max_tokens = int(data.get("max_tokens", 512))
        is_vision = _has_images(messages)

        if is_vision:
            default_vlm = get_extension_config_value(EXT_NAME, "default_vlm_model", "qwen2-vl-2b-instruct")
            vlm_model = model if model in GENAI_MODELS and GENAI_MODELS[model].type == GenAIModelType.VLM else default_vlm
            if not is_hef_available(vlm_model):
                return _openai_error(f"VLM model '{vlm_model}' not downloaded", code="model_not_found", status=404)

            images_bgr = _extract_images(messages)
            if not images_bgr:
                return _openai_error("No decodable images found in messages")

            text_messages = _extract_text_messages(messages)
            user_text = ""
            for msg in reversed(text_messages):
                if msg["role"] == "user":
                    user_text = msg["content"]
                    break
            if not user_text:
                user_text = "Describe this image."
            return await vlm_completion(vlm_model, user_text, images_bgr[0], temperature, max_tokens, stream, model_raw)

        if model not in GENAI_MODELS:
            return _openai_error(f"Model '{model}' not found", code="model_not_found", status=404)
        if GENAI_MODELS[model].type != GenAIModelType.LLM:
            return _openai_error(f"Model '{model}' is not an LLM model", code="invalid_request_error")
        if not is_hef_available(model):
            return _openai_error(f"Model '{model}' not downloaded", code="model_not_found", status=404)

        hailo_messages = _messages_to_hailo_format(_extract_text_messages(messages))
        return await llm_completion(model, hailo_messages, temperature, max_tokens, stream, model_raw)
