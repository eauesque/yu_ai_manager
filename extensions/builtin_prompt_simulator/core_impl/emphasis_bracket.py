"""Bracket weakening and helper functions for emphasis parsing.

Separated from emphasis_parsers.py to keep each module under 300 lines.
"""

from __future__ import annotations

import re
from typing import Any

from core.helpers_core.emphasis_constants import W_NUM

from .emphasis_weight import NAI_BASE, SD_BASE


def find_bracket_weaken(prompt: str, results: list[dict[str, Any]]) -> None:
    """Find bracket weakening [text], [[text]].

    Reports both SD (1/1.1) and NAI (1/1.05) weights since the
    syntax is shared and the calculator cannot know the target engine.
    Also skips SD prompt editing: [from:to:step] patterns.
    """
    i = 0
    while i < len(prompt):
        if prompt[i] == "[":
            # Check for escaped bracket
            if i > 0 and prompt[i - 1] == "\\":
                i += 1
                continue
            depth = 0
            j = i
            while j < len(prompt) and prompt[j] == "[":
                depth += 1
                j += 1
            inner_start = j
            bracket_depth = depth
            k = j
            while k < len(prompt) and bracket_depth > 0:
                if prompt[k] == "[" and not (k > 0 and prompt[k - 1] == "\\"):
                    bracket_depth += 1
                elif prompt[k] == "]" and not (k > 0 and prompt[k - 1] == "\\"):
                    bracket_depth -= 1
                k += 1
            if bracket_depth != 0:
                i = j
                continue
            inner_end = k - depth
            inner = prompt[inner_start:inner_end]
            if not inner.strip():
                i = k
                continue

            # Skip SD prompt editing: [from:to:step] or [text:step]
            if re.match(rf"^[^[\]]+:[^[\]]*:\s*{W_NUM}\s*$", inner):
                i = k
                continue
            if re.match(rf"^[^[\]]+:\s*{W_NUM}\s*$", inner):
                i = k
                continue

            token = prompt[i:k]
            sd_weight = round((1.0 / SD_BASE) ** depth, 6)
            nai_weight = round((1.0 / NAI_BASE) ** depth, 6)
            results.append({
                "token": token,
                "syntax": "sd_weaken",
                "depth": depth,
                "weight": sd_weight,
                "position": i,
            })
            results.append({
                "token": token,
                "syntax": "nai_weaken",
                "depth": depth,
                "weight": nai_weight,
                "position": i,
            })
            i = k
        else:
            i += 1


def is_inside_dp_braces(text: str, pos: int) -> bool:
    """Check if *pos* sits inside a ``{...}`` group that contains top-level ``|``."""
    depth = 0
    left = pos - 1
    brace_start = -1
    while left >= 0:
        if text[left] == "}":
            depth += 1
        elif text[left] == "{":
            if depth == 0:
                brace_start = left
                break
            depth -= 1
        left -= 1
    if brace_start == -1:
        return False

    depth = 0
    right = brace_start
    brace_end = -1
    while right < len(text):
        if text[right] == "{":
            depth += 1
        elif text[right] == "}":
            depth -= 1
            if depth == 0:
                brace_end = right
                break
        right += 1
    if brace_end == -1:
        return False

    inner = text[brace_start + 1:brace_end]
    return has_top_level_pipe(inner)


def has_top_level_pipe(text: str) -> bool:
    """Check if text has a | not inside nested braces."""
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "|" and depth == 0:
            return True
    return False
