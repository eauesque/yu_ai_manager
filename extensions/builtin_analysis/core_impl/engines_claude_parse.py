import json
from typing import Any

from .types import AnalysisResult


def clean_markdown_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned


def _best_effort_json(raw: str, expected_keys: tuple[str, ...]) -> str:
    """Return a JSON-parseable slice of raw, tolerating chatty prose around it.

    Unconstrained local models (no response_format grammar) sometimes wrap
    the requested JSON in commentary despite prompt instructions to not do
    so. Prefer a complete JSON object matching the requested response shape.
    """
    cleaned = clean_markdown_json(raw)
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    fallback = None
    matched = None
    skip_until = 0
    for start, char in enumerate(cleaned):
        if start < skip_until or char not in "{[":
            continue
        try:
            data, end = decoder.raw_decode(cleaned, start)
        except json.JSONDecodeError:
            continue
        candidate = cleaned[start:end]
        skip_until = end
        fallback = candidate
        if isinstance(data, dict) and any(key in data for key in expected_keys):
            matched = candidate
    return matched or fallback or cleaned


def parse_image_analysis(raw: str) -> AnalysisResult:
    result = AnalysisResult()
    result.raw_response = raw
    try:
        data = json.loads(_best_effort_json(raw, (
            "tags", "quality_score", "quality_notes", "description", "style",
            "composition", "mood", "color_palette", "prompt_suggestion",
        )))
        result.tags = data.get("tags", [])
        result.quality_score = float(data.get("quality_score") or 0)
        result.quality_notes = data.get("quality_notes", "")
        result.description = data.get("description", "")
        result.style = data.get("style", "")
        result.composition = data.get("composition", "")
        result.mood = data.get("mood", "")
        result.color_palette = data.get("color_palette", [])
        result.prompt_suggestion = data.get("prompt_suggestion", "")
    except (json.JSONDecodeError, ValueError, AttributeError):
        result.quality_notes = "解析失敗: " + raw[:200]
    return result


def parse_trends_analysis(raw: str) -> dict[str, Any]:
    try:
        return json.loads(_best_effort_json(raw, (
            "frequent_tags", "style_tendency", "strengths", "weaknesses",
            "recommendations", "unexplored",
        )))
    except json.JSONDecodeError:
        return {"raw": raw}
