"""Shared helpers for Agent Safety MCP tools."""

import json


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
