"""VLM OCR JSON extraction utilities.

Handles JSON object/array/JSONL extraction from raw VLM response text.
Separated from vlm_ocr_parsers.py for maintainability.
"""

from __future__ import annotations

import json
import re

from .types import OcrRegion
from .vlm_ocr_prompts import normalize_label

# ── JSON extraction ──


def extract_json_object(raw: str) -> dict:
    """Extract a JSON object from raw VLM response text."""
    # ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    # Direct JSON
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    # Look for { ... } (non-greedy match to extract first object)
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL):
        try:
            result = json.loads(m.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue
    return {}


def extract_json_any(raw: str):
    """Extract JSON (array or object) from raw VLM response text.

    Supported formats:
    - Single JSON array/object
    - ```json ... ``` code block
    - JSONL (one JSON object per line)
    """
    # ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            # If code block content is JSONL
            jsonl = _try_parse_jsonl(m.group(1))
            if jsonl is not None:
                return jsonl
    # Direct JSON
    stripped = raw.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # JSONL (one JSON object per line)
    jsonl = _try_parse_jsonl(stripped)
    if jsonl is not None:
        return jsonl
    # Look for [ ... ] (array)
    m = re.search(r"\[.*\]", stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Look for { ... } (single object -- non-greedy)
    m = re.search(r"\{[^{}]*\}", stripped)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _try_parse_jsonl(text: str) -> list | None:
    """Parse JSONL (one JSON per line) and return as list. Returns None on failure."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    # Simple check if each line starts with {
    if not all(ln.startswith("{") for ln in lines):
        return None
    items = []
    for ln in lines:
        try:
            items.append(json.loads(ln))
        except json.JSONDecodeError:
            return None
    return items


def regions_from_json_array(arr: list) -> list[OcrRegion]:
    """Convert JSON array ([{"text":"...", "type":"..."}]) to region list."""
    regions: list[OcrRegion] = []
    for i, item in enumerate(arr):
        if not isinstance(item, dict):
            continue
        text = item.get("text", "") or item.get("name", "")
        if not text or not text.strip():
            continue
        raw_type = (
            item.get("type", "")
            or item.get("label", "")
            or item.get("category", "")
        )
        raw_conf = item.get("confidence", 0.0)
        try:
            conf = max(0.0, min(1.0, float(raw_conf)))
        except (ValueError, TypeError):
            conf = 0.0
        regions.append(OcrRegion(
            region_id=i + 1,
            bbox=item.get("bbox", []),
            text=text.strip(),
            confidence=conf,
            direction=item.get("direction", "vertical"),
            label=normalize_label(raw_type),
        ))
    return regions


def regions_from_json_object(data: dict) -> list[OcrRegion]:
    """Convert JSON object ({"regions": [...]}) to region list."""
    # "regions" key
    arr = data.get("regions", [])
    if not arr:
        # Also try "texts", "items", or "results" keys
        for key in ("texts", "items", "results", "content"):
            arr = data.get(key, [])
            if arr:
                break
    if not isinstance(arr, list) or not arr:
        return []
    return regions_from_json_array(arr)


def fallback_text(raw: str) -> str:
    """Extract text from raw response when JSON parsing fails."""
    # Remove JSON / code blocks
    text = re.sub(r"```(?:json)?\s*\n?.*?\n?```", "", raw, flags=re.DOTALL)
    text = text.strip()
    return text if text else raw.strip()
