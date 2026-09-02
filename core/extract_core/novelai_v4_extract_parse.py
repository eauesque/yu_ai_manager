"""NovelAI v4 detection and parsing helpers."""

import json


def is_nai_v4_json(text: str) -> bool:
    try:
        outer = json.loads(text)
        if not isinstance(outer, dict) or "Comment" not in outer:
            return False
        inner = json.loads(outer["Comment"])
        return isinstance(inner, dict) and ("v4_prompt" in inner or "v4_negative_prompt" in inner)
    except (json.JSONDecodeError, TypeError):
        return False


def parse_v4_data(comment: str, software: str, raw_meta: str | None) -> tuple[dict | None, str | None]:
    data = None
    raw_override = None

    if software == "NovelAI" and comment:
        try:
            parsed = json.loads(comment)
            if isinstance(parsed, dict):
                data = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    if data is None and raw_meta and is_nai_v4_json(raw_meta):
        try:
            outer = json.loads(raw_meta)
            inner = json.loads(outer["Comment"])
            if isinstance(inner, dict):
                data = inner
                raw_override = raw_meta
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    if not isinstance(data, dict):
        return None, raw_override
    if "v4_prompt" not in data and "v4_negative_prompt" not in data:
        return None, raw_override
    return data, raw_override
