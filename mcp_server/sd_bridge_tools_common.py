"""Shared helpers for SD Bridge MCP tools."""

import json


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def as_error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def strip_base64_images(response):
    if isinstance(response, dict) and "images" in response:
        for image in response.get("images", []):
            if isinstance(image, dict) and "base64" in image:
                image["base64"] = f"(base64, {len(image['base64'])} chars)"
    return response
