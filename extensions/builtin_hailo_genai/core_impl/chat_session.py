"""Hailo Chat session manager — thin wrapper over the chatlog store layer.

Conversation / message persistence delegates to
``extensions.builtin_chatlog.core_impl.store_crud`` so the GenAI extension
shares the same SQL (and the same future fixes) as the chatlog tool. The
``source="hailo"`` constant scopes reads/deletes/renames to GenAI-owned rows
so imported ChatGPT / Claude conversations are not exposed through this
extension's endpoints.

Writes are funneled through ``submit_db_write`` (single writer thread); reads
use the cached thread-local readonly connection. The hailo-specific bits left
in this module are: the active-conversation tracking used by the local LLM
context, and the LLM-prompt assembly.
"""

import logging
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_SOURCE = "hailo"

# Active conversation linked to the local LLM context. Per-process state — the
# Hailo accelerator can only hold one prompt KV cache at a time, so the route
# layer compares against this value to decide whether to clear it.
_active_conv_id: int | None = None
_active_lock = threading.Lock()


def _get_con():
    """Writer-thread connection (only call inside ``submit_db_write``)."""
    from core.services_core.hailo_chat_session_service import get_hailo_chat_write_db
    return get_hailo_chat_write_db()


def _get_ro_con():
    """Readonly thread-local connection (event loop or background thread)."""
    from core.services_core.hailo_chat_session_service import get_hailo_chat_read_db
    return get_hailo_chat_read_db()


def _ensure() -> None:
    from extensions.builtin_chatlog.core_impl.store import ensure_tables
    ensure_tables()


def create_conversation(model: str, title: str = "") -> dict[str, Any]:
    """Create a new conversation. Returns the inserted row as a dict."""
    from core.services_core.db_write import submit_db_write
    from extensions.builtin_chatlog.core_impl.store_crud import insert_conversation

    _ensure()
    now = int(time.time())
    ext_id = str(uuid.uuid4())
    final_title = title or "New Chat"

    def _do_insert() -> int:
        con = _get_con()
        try:
            new_id = insert_conversation(con, {
                "source": _SOURCE,
                "external_id": ext_id,
                "title": final_title,
                "model": model,
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
            })
            con.commit()
        except Exception:
            con.rollback()
            raise
        return new_id

    conv_id = submit_db_write(_do_insert)
    logger.info("新規チャット作成: id=%d, model=%s", conv_id, model)
    return {
        "id": conv_id,
        "source": _SOURCE,
        "external_id": ext_id,
        "title": final_title,
        "model": model,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }


def add_message(conv_id: int, role: str, content: str) -> int:
    """Append a message and return its ``seq``."""
    from core.services_core.db_write import submit_db_write
    from extensions.builtin_chatlog.core_impl.store_crud import append_message

    _ensure()

    def _do_insert() -> int:
        con = _get_con()
        try:
            seq = append_message(con, conv_id, role, content)
            con.commit()
        except Exception:
            con.rollback()
            raise
        return seq

    return submit_db_write(_do_insert)


def auto_title(conv_id: int, first_message: str) -> str:
    """Generate a title from the first message, only if title is still 'New Chat'."""
    from core.services_core.db_write import submit_db_write
    from extensions.builtin_chatlog.core_impl.store_crud import rename_conversation as _rename

    title = first_message.strip()[:60]
    if len(first_message.strip()) > 60:
        title += "..."

    def _do_update() -> None:
        con = _get_con()
        try:
            _rename(con, conv_id, title, source=_SOURCE, only_if_title="New Chat")
            con.commit()
        except Exception:
            con.rollback()
            raise

    submit_db_write(_do_update)
    return title


def rename_conversation(conv_id: int, title: str) -> bool:
    """Change the conversation title (hailo-scoped)."""
    from core.services_core.db_write import submit_db_write
    from extensions.builtin_chatlog.core_impl.store_crud import rename_conversation as _rename

    def _do_update() -> bool:
        con = _get_con()
        try:
            ok = _rename(con, conv_id, title, source=_SOURCE)
            con.commit()
        except Exception:
            con.rollback()
            raise
        return ok

    return submit_db_write(_do_update)


def get_conversation_with_messages(conv_id: int) -> dict[str, Any] | None:
    """Get a hailo-scoped conversation with all messages."""
    from extensions.builtin_chatlog.core_impl.store_crud import get_conversation

    _ensure()
    return get_conversation(_get_ro_con(), conv_id, source=_SOURCE)


def list_conversations_hailo(
    limit: int = 50, offset: int = 0,
) -> list[dict[str, Any]]:
    """List conversations whose source is hailo."""
    from extensions.builtin_chatlog.core_impl.store_crud import list_conversations

    _ensure()
    return list_conversations(_get_ro_con(), source=_SOURCE, limit=limit, offset=offset)


def delete_hailo_conversation(conv_id: int) -> bool:
    """Delete a hailo conversation (cascades to messages via FK)."""
    from core.services_core.db_write import submit_db_write
    from extensions.builtin_chatlog.core_impl.store_crud import delete_conversation

    _ensure()

    def _do_delete() -> bool:
        con = _get_con()
        try:
            result = delete_conversation(con, conv_id, source=_SOURCE)
            con.commit()
            return result
        except Exception:
            con.rollback()
            raise

    return submit_db_write(_do_delete)


def get_recent_messages(conv_id: int, limit: int = 20) -> list[dict[str, str]]:
    """Return recent messages oldest-first for LLM prompt assembly."""
    from extensions.builtin_chatlog.core_impl.store_crud import list_messages_recent

    _ensure()
    return list_messages_recent(_get_ro_con(), conv_id, limit=limit)


def build_llm_prompt(
    conv_id: int,
    system_prompt: str = "You are a helpful assistant.",
    max_history: int = 20,
    extra_context: str = "",
) -> list:
    """Build the multimodal message array for the local LLM.

    ``extra_context`` carries web search results or file contents that should
    be appended to the system prompt before the user turns.
    """
    messages = get_recent_messages(conv_id, limit=max_history)

    sys_content = system_prompt
    if extra_context:
        sys_content += "\n\n" + extra_context
    prompt: list = [{
        "role": "system",
        "content": [{"type": "text", "text": sys_content}],
    }]
    for m in messages:
        prompt.append({
            "role": m["role"],
            "content": [{"type": "text", "text": m["content"]}],
        })
    return prompt


def set_active_conversation(conv_id: int | None) -> int | None:
    """Set the active conversation and return the previous conv_id."""
    global _active_conv_id
    with _active_lock:
        prev = _active_conv_id
        _active_conv_id = conv_id
        return prev


def get_active_conversation() -> int | None:
    """Return the currently active conversation ID."""
    with _active_lock:
        return _active_conv_id
