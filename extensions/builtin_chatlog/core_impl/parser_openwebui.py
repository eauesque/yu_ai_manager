"""Open WebUI conversations.json parser.

Open WebUI export format:
[
  {
    "id": "uuid",
    "title": "conversation title",
    "created_at": 1234567890,
    "updated_at": 1234567891,
    "chat": {
      "history": {
        "messages": {
          "<msg_id>": {
            "id": "<msg_id>",
            "role": "user" | "assistant",
            "content": "...",
            "model": "llama3:latest",
            "timestamp": 1234567890
          }
        },
        "currentId": "<last_msg_id>"
      }
    }
  }
]

messages is in dict format (msg_id -> msg_object).
Linearized by sorting on timestamp.
"""

from __future__ import annotations

from typing import Any

from .parser_claude import ParsedConversation, ParsedMessage


def parse_openwebui_json(data: list) -> list[ParsedConversation]:
    """Parse Open WebUI conversations.json into intermediate format."""
    if not isinstance(data, list):
        return []

    results: list[ParsedConversation] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        ext_id = entry.get("id", "")
        if not ext_id:
            continue

        created_at = _to_int_ts(entry.get("created_at"))
        updated_at = _to_int_ts(entry.get("updated_at"))

        conv = ParsedConversation(
            external_id=ext_id,
            title=entry.get("title", "") or "",
            model="",
            created_at=created_at,
            updated_at=updated_at or created_at,
        )

        chat = entry.get("chat", {})
        if isinstance(chat, dict):
            conv.messages = _extract_messages(chat)
            # Model name: get from first assistant message
            for m in conv.messages:
                if m.role == "assistant" and conv.model == "":
                    conv.model = _get_model_from_msg(chat, m)
                    break

        results.append(conv)

    return results


def _extract_messages(chat: dict[str, Any]) -> list[ParsedMessage]:
    """Extract and sort messages from chat.history.messages dict."""
    history = chat.get("history", {})
    if not isinstance(history, dict):
        return []

    messages_dict = history.get("messages", {})
    if not isinstance(messages_dict, dict):
        return []

    raw_msgs: list[dict[str, Any]] = []
    for _msg_id, msg_obj in messages_dict.items():
        if not isinstance(msg_obj, dict):
            continue
        role = msg_obj.get("role", "")
        if role not in ("user", "assistant", "system"):
            continue
        content = msg_obj.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        raw_msgs.append(msg_obj)

    # Sort by timestamp
    raw_msgs.sort(key=lambda m: _to_int_ts(m.get("timestamp", 0)))

    result: list[ParsedMessage] = []
    for seq, msg in enumerate(raw_msgs):
        result.append(ParsedMessage(
            role=msg.get("role", ""),
            content=msg.get("content", ""),
            created_at=_to_int_ts(msg.get("timestamp", 0)),
            seq=seq,
        ))

    return result


def _get_model_from_msg(chat: dict[str, Any], pm: ParsedMessage) -> str:
    """Get model name from original messages in chat dict."""
    history = chat.get("history", {})
    if not isinstance(history, dict):
        return ""
    messages_dict = history.get("messages", {})
    if not isinstance(messages_dict, dict):
        return ""
    for msg_obj in messages_dict.values():
        if not isinstance(msg_obj, dict):
            continue
        if msg_obj.get("role") == "assistant":
            model = msg_obj.get("model", "")
            if model:
                return model
    return ""


def _to_int_ts(val: Any) -> int:
    """Convert float/int timestamp to int."""
    if val is None:
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0
