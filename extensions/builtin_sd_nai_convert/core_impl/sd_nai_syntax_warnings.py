"""Syntax warning detection for SD/NAI prompt conversion."""

import re

from core.helpers_core.emphasis_constants import W_NUM


def detect_syntax_warnings(prompt: str, mode: str) -> list[dict[str, str]]:
    """Detect mixed NAI/SD syntax in the input and return warnings."""
    warnings: list[dict[str, str]] = []
    # NAI indicators
    has_nai = bool(re.search(rf'{W_NUM}::(?:[^:]|:[^:])+?::', prompt)) or \
              bool(re.search(r'\|\|[^|]+(?:\|[^|]+)*\|\|', prompt)) or \
              bool(re.search(r'\{[^{}|]+\}', prompt))
    # SD indicators
    has_sd = bool(re.search(rf'\([^()]+:{W_NUM}\)', prompt)) or \
             bool(re.search(r'<lora:[^>]+>', prompt, re.I))
    # Shared bracket weakening [tag] — converted by both directions,
    # so its presence means the prompt is NOT "already" in target format.
    has_brackets = bool(re.search(r'\[[^\[\]:]+\]', prompt))

    if has_nai and has_sd:
        warnings.append({"level": "warning", "message": "mixed_syntax"})

    if mode == "nai_to_sd" and has_sd and not has_nai and not has_brackets:
        warnings.append({"level": "info", "message": "already_sd"})
    elif mode == "sd_to_nai" and has_nai and not has_sd and not has_brackets:
        warnings.append({"level": "info", "message": "already_nai"})

    return warnings
