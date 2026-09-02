from core.extensions_core.extensions_admin import get_extension_config_value
from hailo_chat_helpers import clear_llm_context as _clear_llm_context
from quart import jsonify, request

from core.infra_core.blocking_tasks import run_long_blocking_sync

_EXT_NAME = "builtin-hailo-genai"


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_conversation_routes(bp):
    @bp.route("/api/chat/conversations")
    async def api_chat_list():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.chat_session import list_conversations_hailo

        limit = min(int(request.args.get("limit") or 50), 200)
        offset = int(request.args.get("offset") or 0)
        convs = await run_long_blocking_sync(list_conversations_hailo, limit=limit, offset=offset)
        return jsonify({"status": "ok", "conversations": convs})

    @bp.route("/api/chat/conversations/<int:conv_id>")
    async def api_chat_get(conv_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.chat_session import get_conversation_with_messages

        conv = await run_long_blocking_sync(get_conversation_with_messages, conv_id)
        if not conv:
            return jsonify({"status": "error", "message": "Not found"}), 404
        return jsonify({"status": "ok", "conversation": conv})

    @bp.route("/api/chat/conversations/<int:conv_id>", methods=["DELETE"])
    async def api_chat_delete(conv_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.chat_session import (
            delete_hailo_conversation,
            get_active_conversation,
            set_active_conversation,
        )

        if get_active_conversation() == conv_id:
            set_active_conversation(None)
        ok = await run_long_blocking_sync(delete_hailo_conversation, conv_id)
        if not ok:
            return jsonify({"status": "error", "message": "Not found"}), 404
        return jsonify({"status": "ok"})

    @bp.route("/api/chat/conversations/<int:conv_id>/title", methods=["PATCH"])
    async def api_chat_rename(conv_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.chat_session import rename_conversation

        data = await request.get_json(silent=True) or {}
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"status": "error", "message": "title required"}), 400
        ok = await run_long_blocking_sync(rename_conversation, conv_id, title)
        if not ok:
            return jsonify({"status": "error", "message": "Not found"}), 404
        return jsonify({"status": "ok", "title": title})

    @bp.route("/api/chat/new", methods=["POST"])
    async def api_chat_new():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.chat_session import create_conversation, set_active_conversation

        data = await request.get_json(silent=True) or {}
        model = data.get(
            "model",
            get_extension_config_value(
                _EXT_NAME,
                "default_llm_model",
                "qwen3-1.7b-instruct",
            ),
        )
        conv = await run_long_blocking_sync(create_conversation, model=model)
        set_active_conversation(conv["id"])
        _clear_llm_context()
        return jsonify({"status": "ok", "conversation": conv})

    @bp.route("/api/chat/active")
    async def api_chat_active():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from ext_builtin_hailo_genai.core_impl.chat_session import get_active_conversation

        return jsonify({"status": "ok", "conversation_id": get_active_conversation()})
