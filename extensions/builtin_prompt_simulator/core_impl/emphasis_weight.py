"""Emphasis weight calculation engine.

Analyses prompt emphasis tokens and computes effective multipliers.

SD syntax:
  (text)       = 1.1x
  ((text))     = 1.1^2 = 1.21x
  (text:1.5)   = 1.5x

NAI syntax:
  {text}       = 1.05x
  {{text}}     = 1.05^2 = 1.1025x
  [text]       = 1/1.05 = ~0.952x  (weaken)
  weight::text:: = explicit weight (e.g. 1.1::cherry blossoms::)

Parser 関数群は emphasis_parsers.py に分離。
"""

from __future__ import annotations

from typing import Any

from core.helpers_core.emphasis_constants import NAI_BASE, SD_BASE  # noqa: F401


def analyze_emphasis(prompt: str) -> list[dict[str, Any]]:
    """Find all emphasis tokens and compute effective weight."""
    from .emphasis_parsers import (
        find_bracket_weaken,
        find_nai_emphasis,
        find_nai_explicit_weight,
        find_paren_emphasis,
        find_sd_explicit_weight,
    )

    results: list[dict[str, Any]] = []

    # SD explicit weight: (text:weight), possibly wrapped in outer parens
    find_sd_explicit_weight(prompt, results)

    # SD parenthetical emphasis: (text), ((text)), etc.
    find_paren_emphasis(prompt, results)

    # NAI explicit weight: weight::text::
    find_nai_explicit_weight(prompt, results)

    # NAI curly brace emphasis: {text}, {{text}}
    find_nai_emphasis(prompt, results)

    # Bracket weakening: [text], [[text]]
    find_bracket_weaken(prompt, results)

    # Sort by position in prompt
    results.sort(key=lambda r: r.get("position", 0))

    # Remove position field (internal use only)
    for r in results:
        r.pop("position", None)

    return results
