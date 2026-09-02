"""Shared helpers for LLM MCP tools."""

import json


def as_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def as_error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)
