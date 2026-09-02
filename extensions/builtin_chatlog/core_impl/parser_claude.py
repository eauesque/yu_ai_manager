"""Claude conversations.json parser.

Claude export format:
[
  {
    "uuid": "...",
    "name": "conversation title",
    "created_at": "2026-01-01T00:00:00.000000Z",
    "updated_at": "2026-01-01T01:00:00.000000Z",
    "chat_messages": [
      {"sender": "human", "text": "...","created_at":"...","updated_at":"..."},
      {"sender": "assistant", "text": "...", ...}
    ]
  }
]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ParsedMessage:
    role: str
    content: str
    created_at: int
    seq: int


@dataclass
class ParsedConversation:
    external_id: str
    title: str
    model: str
    created_at: int
    updated_at: int
    messages: list[ParsedMessage] = field(default_factory=list)


_ROLE_MAP = {"human": "user", "assistant": "assistant"}


def _parse_iso(s: str) -> int:
    """Convert ISO 8601 string to UNIX timestamp."""
    if not s:
        return 0
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


def parse_claude_json(data: list) -> list[ParsedConversation]:
    """Parse Claude conversations.json into intermediate format."""
    if not isinstance(data, list):
        return []

    results: list[ParsedConversation] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        ext_id = entry.get("uuid", "")
        if not ext_id:
            continue

        conv = ParsedConversation(
            external_id=ext_id,
            title=entry.get("name", "") or "",
            model=_extract_model(entry),
            created_at=_parse_iso(entry.get("created_at", "")),
            updated_at=_parse_iso(entry.get("updated_at", "")),
        )

        raw_msgs = entry.get("chat_messages", [])
        if not isinstance(raw_msgs, list):
            raw_msgs = []

        for seq, msg in enumerate(raw_msgs):
            if not isinstance(msg, dict):
                continue
            sender = msg.get("sender", "")
            role = _ROLE_MAP.get(sender, sender)
            if role not in ("user", "assistant", "system"):
                continue

            text = msg.get("text", "") or ""
            if not text:
                continue

            conv.messages.append(ParsedMessage(
                role=role,
                content=text,
                created_at=_parse_iso(msg.get("created_at", "")),
                seq=seq,
            ))

        conv.updated_at = conv.updated_at or conv.created_at
        results.append(conv)

    return results


def _extract_model(entry: dict[str, Any]) -> str:
    """Extract model name from a conversation entry."""
    model = entry.get("model", "")
    if model:
        return model
    # Claude export may not have model field
    return ""
