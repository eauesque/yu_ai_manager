"""Emphasis parser functions for SD / NAI syntax.

Separated from emphasis_weight.py public API.
Each _find_* function appends match results to the results list.

NOTE: Bracket weakening and helper functions have been moved to
emphasis_bracket.py. This module re-exports all public symbols for
backward compatibility.
"""

from __future__ import annotations

import re
from typing import Any

from core.helpers_core.emphasis_constants import W_NUM, W_SNUM

from .emphasis_bracket import (  # noqa: F401 -- re-export
    find_bracket_weaken,
)
from .emphasis_bracket import (
    has_top_level_pipe as _has_top_level_pipe,
)
from .emphasis_bracket import (
    is_inside_dp_braces as _is_inside_dp_braces,
)
from .emphasis_weight import NAI_BASE, SD_BASE


def find_sd_explicit_weight(prompt: str, results: list[dict[str, Any]]) -> None:
    """Find SD explicit weight (text:weight) including outer parens.

    A1111 behavior: outer parentheses multiply the explicit weight.
    (text:1.5)     = 1.5
    ((text:1.5))   = 1.5 * 1.1   = 1.65
    (((text:1.1))) = 1.1 * 1.1^2 = 1.331
    """
    for m in re.finditer(rf"(?<!\\)\(([^()]+):\s*({W_SNUM})\s*(?<!\\)\)", prompt):
        inner_text = m.group(1)
        # Skip LoRA / embedding references
        if inner_text.startswith(("lora:", "embedding:", "hypernetwork:")):
            continue
        base_weight = float(m.group(2))
        inner_start = m.start()
        inner_end = m.end()

        # Count additional outer parens wrapping this match
        outer_depth = 0
        left = inner_start - 1
        right = inner_end
        while left >= 0 and right < len(prompt) and prompt[left] == "(" and prompt[right] == ")":
            outer_depth += 1
            left -= 1
            right += 1

        effective_weight = base_weight * (SD_BASE ** outer_depth)
        total_depth = 1 + outer_depth
        token_start = inner_start - outer_depth
        token_end = inner_end + outer_depth
        token = prompt[token_start:token_end]

        results.append({
            "token": token,
            "syntax": "sd",
            "depth": total_depth,
            "weight": round(effective_weight, 6),
            "position": token_start,
        })


def find_nai_explicit_weight(prompt: str, results: list[dict[str, Any]]) -> None:
    """Find NAI-style weight::text:: explicit weight tokens.

    Examples: 1.1::cherry blossoms::, -.1::monochrome::, 0::hidden::
    Skips DP weighted choices like {3::red|1::blue} (inside braces with pipes).
    """
    for m in re.finditer(r"(-?\d*\.?\d+)::((?:(?!::).)+)::", prompt):
        # Skip if this match is inside a brace group that has pipes (DP choice)
        start = m.start()
        if _is_inside_dp_braces(prompt, start):
            continue
        results.append({
            "token": m.group(0),
            "syntax": "nai",
            "depth": 1,
            "weight": round(float(m.group(1)), 6),
            "position": m.start(),
        })


def find_paren_emphasis(prompt: str, results: list[dict[str, Any]]) -> None:
    """Find SD-style ((...)) emphasis (not explicit weight)."""
    i = 0
    while i < len(prompt):
        if prompt[i] == "(":
            # Skip escaped parenthesis
            if i > 0 and prompt[i - 1] == "\\":
                i += 1
                continue
            # Count opening depth
            depth = 0
            j = i
            while j < len(prompt) and prompt[j] == "(":
                depth += 1
                j += 1
            # Find matching closing parens
            inner_start = j
            paren_depth = depth
            k = j
            while k < len(prompt) and paren_depth > 0:
                if prompt[k] == "(" and not (k > 0 and prompt[k - 1] == "\\"):
                    paren_depth += 1
                elif prompt[k] == ")" and not (k > 0 and prompt[k - 1] == "\\"):
                    paren_depth -= 1
                k += 1
            if paren_depth != 0:
                i = j
                continue
            inner_end = k - depth
            inner = prompt[inner_start:inner_end]

            # Skip if it's an explicit weight like (text:1.5) or (text: 1.5)
            if re.match(rf"^[^()]+:\s*{W_SNUM}\s*$", inner):
                i = k
                continue
            # Skip if empty
            if not inner.strip():
                i = k
                continue
            # Skip if it looks like a function call or LoRA
            if inner.startswith("embedding:") or inner.startswith("lora:"):
                i = k
                continue

            token = prompt[i:k]
            weight = round(SD_BASE ** depth, 6)
            results.append({
                "token": token,
                "syntax": "sd",
                "depth": depth,
                "weight": weight,
                "position": i,
            })
            i = k
        else:
            i += 1


def find_nai_emphasis(prompt: str, results: list[dict[str, Any]]) -> None:
    """Find NAI-style {{...}} emphasis (not DP choices)."""
    i = 0
    while i < len(prompt):
        if prompt[i] == "{":
            # Skip escaped brace
            if i > 0 and prompt[i - 1] == "\\":
                i += 1
                continue
            depth = 0
            j = i
            while j < len(prompt) and prompt[j] == "{":
                depth += 1
                j += 1
            inner_start = j
            brace_depth = depth
            k = j
            while k < len(prompt) and brace_depth > 0:
                if prompt[k] == "{" and not (k > 0 and prompt[k - 1] == "\\"):
                    brace_depth += 1
                elif prompt[k] == "}" and not (k > 0 and prompt[k - 1] == "\\"):
                    brace_depth -= 1
                k += 1
            if brace_depth != 0:
                i = j
                continue
            inner_end = k - depth
            inner = prompt[inner_start:inner_end]

            # Skip DP choices (contains | at top level)
            if _has_top_level_pipe(inner):
                i = k
                continue
            # Skip weighted syntax (3::text)
            if re.match(rf"^{W_NUM}::", inner):
                i = k
                continue
            # Skip DP pick-N (2$$...)
            if re.match(r"^\d+(?:-\d+)?\$\$", inner):
                i = k
                continue
            if not inner.strip():
                i = k
                continue

            token = prompt[i:k]
            weight = round(NAI_BASE ** depth, 6)
            results.append({
                "token": token,
                "syntax": "nai",
                "depth": depth,
                "weight": weight,
                "position": i,
            })
            i = k
        else:
            i += 1
