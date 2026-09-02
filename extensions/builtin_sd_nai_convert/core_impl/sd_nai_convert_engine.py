"""Prompt conversion engine: Stable Diffusion <-> NovelAI."""

import re

from core.helpers_core.emphasis_constants import NAI_BASE, SD_BASE, W_SNUM

from .sd_nai_convert_emphasis import (
    _safe_close,
    _w,
    convert_nai_emphasis_to_sd,
    convert_sd_emphasis_to_nai,
)
from .sd_nai_convert_escape import protect_escapes, restore_escapes
from .sd_nai_convert_mix import convert_and_to_mixing


def convert_sd_to_nai(prompt: str, *, strip_lora: bool = True, strip_embedding: bool = True, convert_emphasis: bool = True) -> str:
    result = prompt
    if not result:
        return ""

    # Protect escaped brackets from regex processing
    result, _saved_esc = protect_escapes(result)

    if strip_lora:
        result = re.sub(r"<lora:[^>]+>", "", result, flags=re.IGNORECASE)
        result = re.sub(r"<lyco:[^>]+>", "", result, flags=re.IGNORECASE)

    if strip_embedding:
        result = re.sub(r"<(?:embedding|hypernet):[^>]+>", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\(embedding:[^)]+\)", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\bembedding:\S+", "", result, flags=re.IGNORECASE)

    # Convert SD dynamic choices {a|b|c} → NAI ||a|b|c||
    result = re.sub(r"\{([^{}]+(?:\|[^{}]+)+)\}", lambda m: f"||{m.group(1)}||", result)

    # Convert SD weighted (text:weight) → NAI weight::text::
    # Use [^()]+ (allow colons in tag names like artist:5saiji)
    # and match the LAST colon before the weight value.
    # _safe_close inserts a space before the closing :: when the inner text
    # ends with a digit/period, otherwise NAI re-parses the trailing digits
    # as a second numeric weight (e.g. ``1.1::artist:coupe50::`` becomes 50x).
    result = re.sub(
        rf"\(([^()]+?):\s*({W_SNUM})\s*\)",
        lambda m: f"{m.group(2)}::{_safe_close(m.group(1).rstrip())}::",
        result,
    )

    if convert_emphasis:
        result = convert_sd_emphasis_to_nai(result)
        result = _convert_bracket_weaken_to_nai(result)

    if " AND " in result:
        result = convert_and_to_mixing(result)

    result = re.sub(r"\s*,\s*,+", ",", result)
    result = re.sub(r"^\s*,+\s*|\s*,+\s*$", "", result)
    result = re.sub(r"\s{2,}", " ", result)
    result = restore_escapes(result, _saved_esc)
    return result.strip()


def convert_nai_to_sd(prompt: str, *, convert_emphasis: bool = True) -> str:
    result = prompt
    if not result:
        return ""

    # Protect escaped brackets from regex processing
    result, _saved_esc = protect_escapes(result)

    # Convert NAI weight::text:: → SD (text:weight)
    # ``rstrip`` mirrors the SD→NAI direction's space-padding (``_safe_close``)
    # so that round-tripping ``(coupe50:1.2)`` does not leave a stray space
    # before the SD weight colon.
    result = re.sub(
        rf"({W_SNUM})::((?:[^:]|:[^:])+?)::",
        lambda m: f"({m.group(2).rstrip()}:{m.group(1)})",
        result,
    )

    # Convert NAI ||a|b|c|| → SD {a|b|c}
    result = re.sub(r"\|\|([^|]+(?:\|[^|]+)*)\|\|", lambda m: "{" + m.group(1) + "}", result)

    if convert_emphasis:
        result = convert_nai_emphasis_to_sd(result)
        result = _convert_bracket_weaken_to_sd(result)

    # Convert remaining NAI pipe mixing to SD pipe mixing.
    # Only convert plain (non-weighted) pipes to AND;
    # pipes between weighted expressions like (a:0.5)|(b:0.7) are valid SD mixing.
    if "|" in result:
        result = _convert_nai_mixing_to_sd(result)

    result = restore_escapes(result, _saved_esc)
    return result.strip()


def _convert_nai_mixing_to_sd(text: str) -> str:
    """Convert NAI mixing pipes to SD format, preserving valid SD mixing syntax."""
    # Protect randomizer ||...|| and dynamic choices {...|...}
    saved = []

    def _save(m):
        saved.append(m.group(0))
        return f"\x00S{len(saved)-1}\x00"

    protected = re.sub(r"\|\|([^|]+(?:\|[^|]+)*)\|\|", _save, text)
    protected = re.sub(r"\{[^{}]*\|[^{}]*\}", _save, protected)

    if "|" not in protected:
        for i, s in enumerate(saved):
            protected = protected.replace(f"\x00S{i}\x00", s)
        return protected

    parts = protected.split("|")
    # If all parts look like SD weighted mixing (text:weight), keep as pipe
    weighted_re = re.compile(rf"^\s*\([^()]+:{W_SNUM}\)\s*$")
    all_weighted = all(weighted_re.match(p) for p in parts)
    result = "|".join(parts) if all_weighted else " AND ".join(p.strip() for p in parts)

    for i, s in enumerate(saved):
        result = result.replace(f"\x00S{i}\x00", s)
    return result


def _convert_bracket_weaken_to_nai(text: str) -> str:
    """Convert SD [text] weakening to NAI numeric weight::text:: syntax.

    Excludes SD scheduling syntax ``[from:to:step]`` by requiring
    inner content to have no colons.
    """

    def _replace(m: re.Match) -> str:
        full = m.group(0)
        depth = 0
        while depth < len(full) and full[depth] == "[":
            depth += 1
        inner = full[depth:-depth]
        weight = round((1.0 / SD_BASE) ** depth, 6)
        return f"{_w(weight)}::{_safe_close(inner)}::"

    return re.compile(r"\[+([^\[\]:]+)\]+").sub(_replace, text)


def _convert_bracket_weaken_to_sd(text: str) -> str:
    """Convert NAI [text] weakening to SD (text:weight) syntax."""

    def _replace(m: re.Match) -> str:
        full = m.group(0)
        depth = 0
        while depth < len(full) and full[depth] == "[":
            depth += 1
        inner = full[depth:-depth]
        weight = round((1.0 / NAI_BASE) ** depth, 6)
        return f"({inner}:{_w(weight)})"

    return re.compile(r"\[+([^\[\]]+)\]+").sub(_replace, text)
