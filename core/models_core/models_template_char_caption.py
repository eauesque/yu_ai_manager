"""Helpers for extracting materialized character-caption text from template metadata."""

from __future__ import annotations

import json


def extract_char_caption_texts(raw_meta_json: str | None) -> tuple[str, str]:
    if not raw_meta_json:
        return ("", "")
    try:
        outer = json.loads(raw_meta_json)
        if not isinstance(outer, dict):
            return ("", "")
        comment_raw = outer.get("Comment")
        payload = outer
        if isinstance(comment_raw, str):
            try:
                payload = json.loads(comment_raw)
            except Exception:
                payload = outer
        if not isinstance(payload, dict):
            return ("", "")
        positive = _collect_caption_prompts(payload, "v4_prompt")
        negative = _collect_caption_prompts(payload, "v4_negative_prompt")
        return (positive, negative)
    except Exception:
        return ("", "")


def _collect_caption_prompts(payload: dict, key: str) -> str:
    prompt = payload.get(key)
    if not isinstance(prompt, dict):
        return ""
    caption = prompt.get("caption")
    if not isinstance(caption, dict):
        return ""
    parts: list[str] = []
    base_caption = str(caption.get("base_caption") or "").strip()
    if base_caption:
        parts.append(base_caption)
    char_captions = caption.get("char_captions")
    if isinstance(char_captions, list):
        for item in char_captions:
            if not isinstance(item, dict):
                continue
            text = str(item.get("char_caption") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)
