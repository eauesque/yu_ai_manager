"""Server-side lightweight syntax analysis for prompt-syntax extension."""

import re
from typing import Any

from core.helpers_core.emphasis_constants import W_NUM


def _collect_indicators(text: str) -> dict[str, list[str]]:
    indicators: dict[str, list[str]] = {"nai": [], "sd": [], "dp": []}

    for m in re.finditer(rf"{W_NUM}::(?:[^:]|:[^:])+?::", text):
        indicators["nai"].append(m.group())
    for m in re.finditer(r"\|\|[^|]+(?:\|[^|]+)*\|\|", text):
        indicators["nai"].append(m.group())

    for m in re.finditer(rf"\([^()]+:{W_NUM}\)", text):
        indicators["sd"].append(m.group())
    for m in re.finditer(r"<lora:[^>]+>", text, re.IGNORECASE):
        indicators["sd"].append(m.group())
    for m in re.finditer(r"<(?:embedding|hypernet):[^>]+>", text, re.IGNORECASE):
        indicators["sd"].append(m.group())

    for m in re.finditer(r"\{[^{}]+\|[^{}]+\}", text):
        indicators["dp"].append(m.group())
    for m in re.finditer(r"__[a-zA-Z0-9_\-/]+__", text):
        indicators["dp"].append(m.group())

    return indicators


def _detect_syntax(indicators: dict[str, list[str]]) -> str:
    has_nai = len(indicators["nai"]) > 0
    has_sd = len(indicators["sd"]) > 0
    has_dp = len(indicators["dp"]) > 0

    if has_nai and has_sd:
        return "mixed"
    if has_nai:
        return "nai"
    if has_sd:
        return "sd"
    if has_dp:
        return "dynamic_prompts"
    return "unknown"


def _balance_warnings(text: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for open_ch, close_ch, name in [("(", ")", "丸括弧"), ("{", "}", "波括弧"), ("[", "]", "角括弧")]:
        depth = 0
        for ch in text:
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
        if depth != 0:
            warnings.append({"level": "error", "message": f"{name}の数が一致しません（差: {depth:+d}）"})
    return warnings


def analyze_prompt_text(text: str) -> tuple[dict[str, Any], int]:
    """Return analysis payload and HTTP status code."""
    if not text:
        return {"error": "No text provided"}, 400

    indicators = _collect_indicators(text)
    syntax = _detect_syntax(indicators)
    warnings = []

    if len(indicators["nai"]) > 0 and len(indicators["sd"]) > 0:
        warnings.append({"level": "warning", "message": "NAI構文とSD構文が混在しています"})

    warnings.extend(_balance_warnings(text))

    return {
        "syntax": syntax,
        "indicators": {k: len(v) for k, v in indicators.items()},
        "warnings": warnings,
        "tag_count": len([t for t in text.split(",") if t.strip()]),
    }, 200
