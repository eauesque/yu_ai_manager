"""Shared helpers for LoRA dataset MCP tools."""

import json


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
