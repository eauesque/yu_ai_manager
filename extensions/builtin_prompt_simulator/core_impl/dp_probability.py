"""Dynamic Prompts probability analysis engine.

Supported syntax:
  - {a|b|c}            — uniform random (1/n each)
  - {3::red|1::blue}   — weighted choice
  - {2$$a|b|c|d}       — pick N
  - {1-3$$a|b|c|d}     — pick N-M range
  - {2$$ and $$a|b|c}  — custom separator (ignored for probability)
  - nested: {a|{b|c}}  — recursive analysis
"""

from __future__ import annotations

import re
from math import comb
from typing import Any

from core.helpers_core.emphasis_constants import W_NUM


def analyze_dp_choices(prompt: str) -> list[dict[str, Any]]:
    """Find all DP choice expressions and compute per-choice probability."""
    results: list[dict[str, Any]] = []
    _find_choices(prompt, results)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WEIGHT_PREFIX = re.compile(rf"^({W_NUM})::")


def _find_choices(text: str, out: list[dict[str, Any]]) -> None:
    """Walk *text* and extract top-level brace groups."""
    i = 0
    while i < len(text):
        if text[i] == "{":
            end = _find_matching_brace(text, i)
            if end == -1:
                i += 1
                continue
            inner = text[i + 1 : end]
            expr = text[i : end + 1]
            _analyze_one(expr, inner, out)
            i = end + 1
        else:
            i += 1


def _find_matching_brace(text: str, start: int) -> int:
    """Return index of matching '}' for '{' at *start*, or -1."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level(inner: str) -> list[str]:
    """Split *inner* by top-level '|' (respecting nested braces)."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in inner:
        if ch == "{":
            depth += 1
            cur.append(ch)
        elif ch == "}":
            depth -= 1
            cur.append(ch)
        elif ch == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _analyze_one(
    expr: str, inner: str, out: list[dict[str, Any]]
) -> None:
    """Analyze a single brace expression."""
    # Detect pick-N prefix: {2$$...} or {1-3$$...} or {2$$ sep $$...}
    pick_match = re.match(r"^(\d+)(?:-(\d+))?\$\$(?:([^$]*)\$\$)?(.*)", inner, re.S)
    if pick_match:
        pick_min = int(pick_match.group(1))
        pick_max = int(pick_match.group(2)) if pick_match.group(2) else pick_min
        rest = pick_match.group(4)
        choices = _split_top_level(rest)
        choices = [c.strip() for c in choices if c.strip()]
        total = len(choices)
        if total == 0:
            return

        if pick_min == pick_max:
            n = min(pick_min, total)
            combos = comb(total, n)
            prob_each = n / total if total > 0 else 0
            entry: dict[str, Any] = {
                "expression": expr,
                "type": "pick_n",
                "pick": n,
                "total": total,
                "combinations": combos,
                "choices": [
                    {"text": c, "probability": round(prob_each, 6)}
                    for c in choices
                ],
            }
        else:
            lo = min(pick_min, total)
            hi = min(pick_max, total)
            combos = sum(comb(total, k) for k in range(lo, hi + 1))
            # Average selection probability across the range
            avg_picks = sum(range(lo, hi + 1)) / (hi - lo + 1)
            prob_each = avg_picks / total if total > 0 else 0
            entry = {
                "expression": expr,
                "type": "pick_range",
                "pick_min": lo,
                "pick_max": hi,
                "total": total,
                "combinations": combos,
                "choices": [
                    {"text": c, "probability": round(prob_each, 6)}
                    for c in choices
                ],
            }
        out.append(entry)
        # Recurse into each choice for nested expressions
        for c in choices:
            _find_choices(c, out)
        return

    # Normal choice (uniform or weighted)
    parts = _split_top_level(inner)
    if len(parts) < 2:
        # Not a choice expression (single element like {emphasis})
        return

    # Check for weighted syntax: {3::red|1::blue}
    weighted_parts: list[tuple[str, float]] = []
    all_weighted = True
    for p in parts:
        p_stripped = p.strip()
        wm = _WEIGHT_PREFIX.match(p_stripped)
        if wm:
            weight = float(wm.group(1))
            text = p_stripped[wm.end():].strip()
            weighted_parts.append((text, weight))
        else:
            all_weighted = False
            weighted_parts.append((p_stripped, 1.0))

    total_weight = sum(w for _, w in weighted_parts)
    if total_weight == 0:
        return

    if all_weighted and any(w != 1.0 for _, w in weighted_parts):
        entry = {
            "expression": expr,
            "type": "weighted",
            "choices": [
                {
                    "text": text,
                    "weight": weight,
                    "probability": round(weight / total_weight, 6),
                }
                for text, weight in weighted_parts
            ],
        }
    else:
        n = len(weighted_parts)
        entry = {
            "expression": expr,
            "type": "uniform",
            "choices": [
                {"text": text, "probability": round(1.0 / n, 6)}
                for text, _ in weighted_parts
            ],
        }

    out.append(entry)
    # Recurse into each choice
    for text, _ in weighted_parts:
        _find_choices(text, out)
