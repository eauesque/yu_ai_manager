"""Shared helpers for OCR MCP tools."""

from __future__ import annotations

import json


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
