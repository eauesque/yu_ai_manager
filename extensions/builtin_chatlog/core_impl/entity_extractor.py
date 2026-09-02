"""Regex-based entity extraction engine.

Automatically extracts bug IDs, version numbers, file paths, function names,
and class names from conversation messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Entity:
    """An extracted entity."""
    entity_type: str
    entity_value: str
    message_id: int | None = None


# Entity extraction patterns
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Ticket IDs like BUG-123, ISSUE-456
    ("bug", re.compile(r"\b([A-Z]+-\d+)\b")),
    # Version numbers: v1.2.3, v2.87.0 etc.
    ("version", re.compile(r"\b(v\d+\.\d+(?:\.\d+)?)\b")),
    # File paths: foo.py, bar/baz.ts, config.json etc.
    ("file", re.compile(
        r"\b([\w./-]+\.(?:py|ts|js|json|html|css|md|yaml|yml|toml|sql|sh|rs|go))\b"
    )),
    # Python function definitions: def foo_bar(
    ("function", re.compile(r"\bdef\s+(\w+)\s*\(")),
    # Python/TS class definitions: class FooBar
    ("class", re.compile(r"\bclass\s+([A-Z]\w*)\b")),
]

# Exclude too-short filenames (extension only, etc.)
_MIN_FILE_LENGTH = 4


def extract_entities(text: str) -> list[Entity]:
    """Extract entities from text.

    Returns deduplicated results.
    """
    seen: set[tuple[str, str]] = set()
    results: list[Entity] = []

    for entity_type, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1)

            # Exclude too-short file paths
            if entity_type == "file" and len(value) < _MIN_FILE_LENGTH:
                continue

            key = (entity_type, value)
            if key not in seen:
                seen.add(key)
                results.append(Entity(entity_type=entity_type, entity_value=value))

    return results


def extract_from_conversation(
    messages: list[dict],
) -> list[dict]:
    """Extract entities from all messages in a conversation.

    Deduplicated (same type+value within a conversation is merged into one record).
    message_id uses the id of the first message where it appeared.

    Args:
        messages: List of message dicts (must have id and content keys)

    Returns:
        List of entity dicts
    """
    seen: set[tuple[str, str]] = set()
    results: list[dict] = []

    for msg in messages:
        content = msg.get("content", "")
        msg_id = msg.get("id")

        if not content:
            continue

        for entity in extract_entities(content):
            key = (entity.entity_type, entity.entity_value)
            if key not in seen:
                seen.add(key)
                results.append({
                    "entity_type": entity.entity_type,
                    "entity_value": entity.entity_value,
                    "message_id": msg_id,
                })

    return results
