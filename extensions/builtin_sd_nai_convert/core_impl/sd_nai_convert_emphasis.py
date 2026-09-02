"""Emphasis conversion helpers for SD/NAI prompt conversion.

Converts emphasis brackets to explicit numeric weight syntax
to preserve mathematical accuracy across different base multipliers
(SD 1.1x vs NAI 1.05x).

Uses single-bracket regex + while loop to peel one layer at a time.
``((bold))`` is processed as:
  1. inner ``(bold)`` → ``1.1::bold::``
  2. outer ``(1.1::bold::)`` → merge → ``1.21::bold::``
"""

import re

from core.helpers_core.emphasis_constants import NAI_BASE, SD_BASE

from .sd_nai_convert_escape import protect_escapes, restore_escapes

# NAI weight::text:: pattern for detecting already-converted segments
_NAI_WT_RE = re.compile(r"(-?\d*\.?\d+)::((?:[^:]|:[^:])*?)::")


def _w(w: float) -> str:
    """Format weight as string, rounding to 6 decimal places."""
    return str(round(w, 6))


def _safe_close(text: str) -> str:
    """Pad ``text`` so its closing ``::`` is unambiguous to the NAI parser.

    NAI's ``::`` weight syntax greedily consumes any trailing digits or a
    trailing period as a numeric weight (see SD_NAI_PROMPT_SYNTAX_SPEC.md
    §2.4 — ``year 2002::`` is parsed as text=``year `` weight=``2002``).
    Inserting a single space before the closing ``::`` breaks that parse
    (``year 2002 ::`` → text=``year 2002``, no spurious extra weight).

    Returns ``text`` unchanged when the last character cannot start a
    ``W_SNUM`` token, so well-formed inputs are not bloated.
    """
    if text and text[-1] in "0123456789.":
        return text + " "
    return text


def convert_sd_emphasis_to_nai(text: str) -> str:
    """Convert SD () emphasis to NAI numeric weight::text:: syntax.

    Peels one layer of parentheses per iteration.  The while loop
    handles arbitrary nesting depth by multiplying weights via
    ``_merge_nai_weights`` when inner content already contains
    ``weight::text::`` segments.
    """
    text, saved = protect_escapes(text)

    def _replace(m: re.Match) -> str:
        inner = m.group(1)
        if "::" in inner:
            return _merge_nai_weights(inner, SD_BASE)
        return f"{_w(SD_BASE)}::{_safe_close(inner)}::"

    # Single bracket: exactly one ( and one ) — peel innermost first
    pattern = re.compile(r"\(([^()]+)\)")
    while pattern.search(text):
        text = pattern.sub(_replace, text)
    return restore_escapes(text, saved)


def _merge_nai_weights(inner: str, multiplier: float) -> str:
    """Merge nested NAI weight::text:: segments with an outer multiplier.

    For content like ``1.1::tag2::`` wrapped in an outer ``()``,
    multiply the existing weight (1.1 * 1.1 = 1.21) and apply
    the multiplier to any plain-text segments as well.
    """
    parts: list[str] = []
    last_end = 0
    for m in _NAI_WT_RE.finditer(inner):
        before = inner[last_end:m.start()].strip().strip(",").strip()
        if before:
            parts.append(f"{_w(multiplier)}::{_safe_close(before)}::")
        inner_w = float(m.group(1))
        combined = round(inner_w * multiplier, 6)
        parts.append(f"{_w(combined)}::{_safe_close(m.group(2))}::")
        last_end = m.end()
    after = inner[last_end:].strip().strip(",").strip()
    if after:
        parts.append(f"{_w(multiplier)}::{_safe_close(after)}::")
    return ", ".join(parts)


def convert_nai_emphasis_to_sd(text: str) -> str:
    """Convert NAI {} emphasis to SD (text:weight) syntax.

    Peels one layer of braces per iteration, same strategy as
    ``convert_sd_emphasis_to_nai``.
    """
    text, saved = protect_escapes(text)
    _sd_wt_re = re.compile(r"\(([^():]+):(-?\d*\.?\d+)\)")

    def _replace(m: re.Match) -> str:
        inner = m.group(1)
        if "|" in inner:
            return m.group(0)
        if _sd_wt_re.search(inner):
            return _merge_sd_weights(inner, NAI_BASE, _sd_wt_re)
        return f"({inner}:{_w(NAI_BASE)})"

    # Single bracket: exactly one { and one }
    pattern = re.compile(r"\{([^{}]+)\}")
    prev = None
    while prev != text:
        prev = text
        text = pattern.sub(_replace, text)
    return restore_escapes(text, saved)


def _merge_sd_weights(inner: str, multiplier: float, sd_re: re.Pattern) -> str:
    """Merge nested SD (text:weight) segments with an outer multiplier."""
    parts: list[str] = []
    last_end = 0
    for m in sd_re.finditer(inner):
        before = inner[last_end:m.start()].strip().strip(",").strip()
        if before:
            parts.append(f"({before}:{_w(multiplier)})")
        inner_text = m.group(1)
        inner_w = float(m.group(2))
        combined = round(inner_w * multiplier, 6)
        parts.append(f"({inner_text}:{_w(combined)})")
        last_end = m.end()
    after = inner[last_end:].strip().strip(",").strip()
    if after:
        parts.append(f"({after}:{_w(multiplier)})")
    return ", ".join(parts)
