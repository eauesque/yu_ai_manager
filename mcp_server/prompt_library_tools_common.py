"""Shared helpers for Prompt Library MCP tools."""

import json

_PFX = "/ext/prompt-library"


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
