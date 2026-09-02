"""ChatGPT conversations.json parser.

ChatGPT export format:
[
  {
    "id": "...",
    "title": "conversation title",
    "create_time": 1234567890.0,
    "update_time": 1234567891.0,
    "mapping": {
      "node_id_1": {
        "id": "node_id_1",
        "parent": null,
        "children": ["node_id_2"],
        "message": null  // root node
      },
      "node_id_2": {
        "id": "node_id_2",
        "parent": "node_id_1",
        "children": ["node_id_3"],
        "message": {
          "author": {"role": "user"},
          "content": {"content_type": "text", "parts": ["..."]},
          "create_time": 1234567890.0
        }
      }
    }
  }
]
"""

from __future__ import annotations

from typing import Any

from .parser_claude import ParsedConversation, ParsedMessage


def parse_chatgpt_json(data: list) -> list[ParsedConversation]:
    """Parse ChatGPT conversations.json into intermediate format."""
    if not isinstance(data, list):
        return []

    results: list[ParsedConversation] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        ext_id = entry.get("id", "")
        if not ext_id:
            continue

        create_time = _to_int_ts(entry.get("create_time"))
        update_time = _to_int_ts(entry.get("update_time"))

        conv = ParsedConversation(
            external_id=ext_id,
            title=entry.get("title", "") or "",
            model=_extract_model(entry),
            created_at=create_time,
            updated_at=update_time or create_time,
        )

        mapping = entry.get("mapping", {})
        if isinstance(mapping, dict):
            conv.messages = _linearize_mapping(mapping)

        results.append(conv)

    return results


def _linearize_mapping(mapping: dict[str, Any]) -> list[ParsedMessage]:
    """Traverse mapping node tree via children[0] and convert to linear message sequence."""
    # Find root node (parent is None)
    root_id = _find_root(mapping)
    if not root_id:
        return []

    messages: list[ParsedMessage] = []
    seq = 0
    current_id: str | None = root_id

    while current_id:
        node = mapping.get(current_id)
        if not node or not isinstance(node, dict):
            break

        msg_data = node.get("message")
        if msg_data and isinstance(msg_data, dict):
            parsed = _parse_node_message(msg_data, seq)
            if parsed:
                messages.append(parsed)
                seq += 1

        # Follow children[0] (branching = regeneration uses first response)
        children = node.get("children", [])
        current_id = children[0] if children and isinstance(children, list) else None

    return messages


def _find_root(mapping: dict[str, Any]) -> str | None:
    """Find the root node whose parent is None."""
    for node_id, node in mapping.items():
        if not isinstance(node, dict):
            continue
        if node.get("parent") is None:
            return node_id
    return None


def _parse_node_message(msg_data: dict[str, Any], seq: int) -> ParsedMessage | None:
    """Convert a mapping node message to ParsedMessage."""
    author = msg_data.get("author", {})
    if not isinstance(author, dict):
        return None

    role = author.get("role", "")
    if role not in ("user", "assistant", "system"):
        return None

    content_obj = msg_data.get("content", {})
    if not isinstance(content_obj, dict):
        return None

    parts = content_obj.get("parts", [])
    if not isinstance(parts, list):
        return None

    # Extract only strings from parts (skip dicts like images)
    text_parts = [p for p in parts if isinstance(p, str)]
    text = "\n".join(text_parts).strip()
    if not text:
        return None

    created_at = _to_int_ts(msg_data.get("create_time"))

    return ParsedMessage(
        role=role,
        content=text,
        created_at=created_at,
        seq=seq,
    )


def _extract_model(entry: dict[str, Any]) -> str:
    """Extract model name from a conversation entry."""
    # ChatGPT export may lack model field at top level
    # Try to get from metadata in assistant messages within mapping
    mapping = entry.get("mapping", {})
    if not isinstance(mapping, dict):
        return ""
    for node in mapping.values():
        if not isinstance(node, dict):
            continue
        msg = node.get("message")
        if not isinstance(msg, dict):
            continue
        author = msg.get("author", {})
        if not isinstance(author, dict):
            continue
        if author.get("role") != "assistant":
            continue
        metadata = msg.get("metadata", {})
        if isinstance(metadata, dict):
            model = metadata.get("model_slug", "")
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
