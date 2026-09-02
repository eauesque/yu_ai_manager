"""Shared helpers for ComfyUI Bridge MCP tools."""

import json


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def as_error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)
