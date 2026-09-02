"""NovelAI metadata extraction helpers."""

import json
from typing import Any


def format_novelai_v4_prompt(caption: dict[str, Any]) -> str:
    """Format NovelAI V4 caption dict into text prompt."""
    parts = []

    if "base_caption" in caption and caption["base_caption"]:
        parts.append(caption["base_caption"])

    if "char_captions" in caption:
        for char in caption["char_captions"]:
            if isinstance(char, dict) and "char_caption" in char:
                parts.append(char["char_caption"])

    return ", ".join(parts) if parts else ""


def extract_novelai(info: dict[str, Any], ext: str) -> tuple[str | None, str | None, str, str | None]:
    """Extract NovelAI V3/V4 metadata payload."""
    if "Comment" in info:
        try:
            comment = json.loads(info["Comment"])
            if "v4_prompt" in comment or "v4_negative_prompt" in comment:
                positive = None
                negative = None

                if "v4_prompt" in comment:
                    v4_prompt = comment["v4_prompt"]
                    if isinstance(v4_prompt, dict) and "caption" in v4_prompt:
                        positive = format_novelai_v4_prompt(v4_prompt["caption"])

                if "v4_negative_prompt" in comment:
                    v4_neg = comment["v4_negative_prompt"]
                    if isinstance(v4_neg, dict) and "caption" in v4_neg:
                        negative = format_novelai_v4_prompt(v4_neg["caption"])

                fmt = f"novelai_v4_{ext[1:]}"
                return (positive, negative, fmt, info["Comment"])
        except (json.JSONDecodeError, KeyError):
            pass

    positive = None
    negative = None

    if "Description" in info:
        positive = info["Description"]
    elif "Comment" in info:
        positive = info["Comment"]

    if "Title" in info and info["Title"].startswith("uc: "):
        negative = info["Title"][4:]

    fmt = f"novelai_v3_{ext[1:]}"
    raw_meta = {
        "Title": info.get("Title"),
        "Description": info.get("Description"),
        "Comment": info.get("Comment"),
        "Source": info.get("Source"),
        "Software": info.get("Software"),
    }
    return (positive, negative, fmt, json.dumps(raw_meta, ensure_ascii=False))
