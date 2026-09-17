import asyncio
import json
import logging

from core.extensions_core.extensions_admin import get_extension_config_value
from hailo_chat_helpers import (
    clear_llm_context as _clear_llm_context,
)
from hailo_chat_helpers import (
    parse_send_request as _parse_send_request,
)
from hailo_chat_helpers import (
    prepare_image as _prepare_image,
)
from hailo_chat_helpers import (
    stream_vlm_response as _stream_vlm_response,
)
from openai_helpers import _validate_generation_request_types
from quart import Response, jsonify, request

logger = logging.getLogger(__name__)
_EXT_NAME = "builtin-hailo-genai"


def register_send_routes(bp):
    @bp.route("/api/chat/send", methods=["POST"])
    async def api_chat_send():
        from ext_builtin_hailo_genai.core_impl.chat_session import (
            add_message,
            auto_title,
            build_llm_prompt,
            create_conversation,
            get_active_conversation,
            get_conversation_with_messages,
            set_active_conversation,
        )
        from ext_builtin_hailo_genai.core_impl.model_download import is_hef_available

        data = await _parse_send_request()
        if err := _validate_generation_request_types(data, max_tokens_field="max_tokens"):
            return jsonify({"status": "error", "message": err}), 400
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"status": "error", "message": "content is required"}), 400

        params = _extract_send_params(data)
        image_file = data.get("_image_file")
        file_id = data.get("file_id")
        frames, has_image, err = _prepare_request_image(image_file, file_id)
        if err:
            return jsonify({"status": "error", "message": err}), 400
        if has_image and not is_hef_available(params["vlm_model"]):
            return jsonify({"status": "error", "message": f"VLM model '{params['vlm_model']}' not downloaded"}), 400

        search_results, search_augmented = await _prepare_search_context(content, params["web_search"])
        if not has_image and not is_hef_available(params["model"]):
            return jsonify({"status": "error", "message": f"Model '{params['model']}' not downloaded"}), 400

        # SQLITE_IMPLEMENTATION_GUIDE §3.3: sync DB I/O must not run on the
        # event loop. submit_db_write blocks on future.result(); readonly
        # SELECT and connection-open (~250-490 ms PBKDF2 derivation on first
        # touch per thread) also stall the loop. Offload every DB touch to a
        # worker thread so concurrent requests (chatlog, lan_cowork heartbeat)
        # keep flowing while this handler waits on the writer queue.
        conv_id = await asyncio.to_thread(
            _ensure_conversation,
            params["conversation_id"], params["model"],
            get_conversation_with_messages, create_conversation,
        )
        if conv_id is None:
            return jsonify({"status": "error", "message": "Conversation not found"}), 404

        prev_active = get_active_conversation()
        if prev_active != conv_id:
            _clear_llm_context()
            set_active_conversation(conv_id)

        msg_content = f"[Image] {content}" if has_image else content
        await asyncio.to_thread(add_message, conv_id, "user", msg_content)

        conv_data = await asyncio.to_thread(get_conversation_with_messages, conv_id)
        user_msgs = [m for m in (conv_data or {}).get("messages", []) if m["role"] == "user"]
        new_title = (
            await asyncio.to_thread(auto_title, conv_id, content)
            if len(user_msgs) == 1 else None
        )

        if has_image:
            return _stream_vlm_response(
                conv_id,
                content,
                frames,
                params["temperature"],
                params["max_tokens"],
                new_title,
                search_results,
                add_message,
                vlm_model=params["vlm_model"],
            )

        prompt = await asyncio.to_thread(
            build_llm_prompt, conv_id,
            system_prompt=params["system_prompt"], extra_context="",
        )
        _inject_search_message(prompt, search_augmented)
        resp = Response(
            _generate_sse(conv_id, prompt, params["model"], params["temperature"], params["max_tokens"], new_title, search_results, add_message),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        resp.timeout = None  # disable Quart RESPONSE_TIMEOUT (60s default) for SSE
        return resp

    @bp.route("/api/chat/search", methods=["POST"])
    async def api_chat_search():
        from ext_builtin_hailo_genai.core_impl.web_search import search_web

        data = await request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"status": "error", "message": "query is required"}), 400
        max_results = min(int(data.get("max_results", 5)), 10)
        results = await asyncio.to_thread(search_web, query, max_results=max_results)
        return jsonify({"status": "ok", "results": results, "query": query})


def _extract_send_params(data):
    return {
        "conversation_id": data.get("conversation_id"),
        "model": data.get("model", get_extension_config_value(_EXT_NAME, "default_llm_model", "qwen3-1.7b-instruct")),
        "vlm_model": data.get("vlm_model", get_extension_config_value(_EXT_NAME, "default_vlm_model", "qwen2-vl-2b-instruct")),
        "temperature": float(data.get("temperature", get_extension_config_value(_EXT_NAME, "temperature", 0.7))),
        "max_tokens": int(data.get("max_tokens", get_extension_config_value(_EXT_NAME, "max_generated_tokens", 512))),
        "system_prompt": data.get("system_prompt", "You are a helpful assistant."),
        "web_search": data.get("web_search", False),
    }


def _prepare_request_image(image_file, file_id):
    frames = None
    has_image = False
    if image_file or file_id:
        frames, err = _prepare_image(image_file, file_id)
        if err:
            return None, False, err
        has_image = True
    return frames, has_image, None


async def _prepare_search_context(content: str, web_search: bool):
    if not web_search:
        return None, None
    from ext_builtin_hailo_genai.core_impl.web_search import format_search_context, search_web

    search_results = await asyncio.to_thread(search_web, content, max_results=5)
    search_ctx = format_search_context(search_results, content)
    if not search_ctx:
        return search_results, None
    return search_results, f"{search_ctx}\n\nBased on the search results above, answer this question: {content}"


def _ensure_conversation(conv_id, model, get_conversation_with_messages, create_conversation):
    if conv_id:
        try:
            conv_id = int(conv_id)
        except (TypeError, ValueError):
            conv_id = None
    if not conv_id:
        return create_conversation(model=model)["id"]
    return conv_id if get_conversation_with_messages(conv_id) else None


def _inject_search_message(prompt, search_augmented):
    if not search_augmented or not prompt:
        return
    for i in range(len(prompt) - 1, -1, -1):
        if prompt[i].get("role") == "user":
            prompt[i]["content"] = [{"type": "text", "text": search_augmented}]
            return


async def _generate_sse(conv_id, prompt, model, temperature, max_tokens, new_title, search_results, add_message):
    try:
        from ext_builtin_hailo_genai.core_impl.llm_control import async_close_vlm
        from ext_builtin_hailo_genai.core_impl.llm_inference import (
            HailoBusyError,
            HailoLLMSubprocessClient,
            get_llm,
            stream_with_keepalive,
            use_subprocess,
        )

        from core.configuration.api import load_config_json

        config = load_config_json(None)
        # Free the VLM (subprocess mode → ControlMessage; otherwise direct)
        # so the LLM can claim the NPU.
        await async_close_vlm(config)

        init_data = {"conversation_id": conv_id, "title": new_title}
        if search_results:
            init_data["search_results"] = search_results
        yield f"data: {json.dumps(init_data)}\n\n"

        full_text: list[str] = []
        overflow_failed = False

        if use_subprocess(config):
            import uuid

            from core.inference_worker.bridge import inference_bridge

            client = HailoLLMSubprocessClient(inference_bridge, uuid.uuid4().hex, model)
            try:
                stream = client.stream(prompt, temperature=temperature, max_tokens=max_tokens)
                async for kind, tok in stream_with_keepalive(stream):
                    if kind == "ping":
                        yield f"data: {json.dumps({'keepalive': True})}\n\n"
                        continue
                    if isinstance(tok, str):
                        full_text.append(tok)
                        yield f"data: {json.dumps({'token': tok})}\n\n"
                    else:
                        overflow_failed = True
                        yield f"data: {json.dumps({'error': tok.error or 'stream_error'})}\n\n"
                        break
            except HailoBusyError:
                # NPU busy (e.g. concurrent batch analysis holding the lock).
                # SSE cannot set retry_after as an HTTP header at this point
                # (headers already flushed), so surface it in the event body
                # for the chat UI to read.
                yield f"data: {json.dumps({'error': 'hailo_npu_busy', 'retry_after': 30})}\n\n"
                return
        else:
            llm = await asyncio.to_thread(get_llm, model)
            it = iter(llm.generate_stream(prompt, temperature=temperature, max_generated_tokens=max_tokens))
            while True:
                token = await asyncio.to_thread(next, it, None)
                if token is None:
                    break
                full_text.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"

        if overflow_failed:
            return

        assistant_text = "".join(full_text)
        await asyncio.to_thread(add_message, conv_id, "assistant", assistant_text)
        yield f"data: {json.dumps({'done': True, 'full_text': assistant_text, 'conversation_id': conv_id})}\n\n"
    except Exception:
        logger.exception("LLM chat SSE generation failed")
        yield f"data: {json.dumps({'error': 'Chat generation failed'})}\n\n"
