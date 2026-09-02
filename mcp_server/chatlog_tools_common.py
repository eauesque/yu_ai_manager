"""Shared helpers for Chatlog MCP tools."""

import json

_PFX = "/ext/chatlog"


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
