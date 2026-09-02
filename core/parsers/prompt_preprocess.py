"""Shared prompt pre-processing pipeline.

Strips syntax-level control tokens (BREAK, alternation, LoRA blocks,
brace emphasis, etc.) *before* the comma-split / candidate-parse phase.
Both ``core.parsers.prompt_parse`` and ``core.tagdb_prompt.parse`` call
``preprocess_prompt_text()`` as the first transformation step.
"""

import re

from core.helpers_core.emphasis_constants import SD_ALTERNATION_RE as _SD_ALTERNATION_RE

# BUG-36: BREAK keyword (word-boundary, case-sensitive)
_BREAK_RE = re.compile(r"(?<![a-zA-Z])BREAK(?![a-zA-Z])")

# BUG-60: <break> HTML-style tag (case-insensitive)
_BREAK_TAG_RE = re.compile(r"<break>", re.IGNORECASE)

# BUG-37: bare ``::`` that is NOT preceded by a digit (NAI weight prefix)
_BARE_COLON_RE = re.compile(r"(?<!\d)::(?!\d)")

# BUG-44: NAI brace emphasis  {word} / {{word}}  (no pipe inside)
_BRACE_EMPHASIS_RE = re.compile(r"\{+([^{}|]+?)\}+")

# BUG-56: Wildcard variables  ${var}, ${30}
_WILDCARD_VAR_RE = re.compile(r"\$\{[^}]*\}")

# BUG-33: angle-bracket blocks  <lora:...>, <hypernet:...>, etc.
_ANGLE_BLOCK_RE = re.compile(r"<[^>]+>")

# BUG-34: adjacent weight groups  (tag:1.3)(tag:1.5) or (tag:1.3) and (tag:1.5)
_ADJACENT_WEIGHT_RE = re.compile(r"\)\s*(?:(?:and|AND)\s+)?(?=\()")


def strip_sd_alternation(text: str) -> str:
    """BUG-35: Remove ``[from:to:0.7]`` alternation syntax."""
    return _SD_ALTERNATION_RE.sub("", text)


def strip_break_keyword(text: str) -> str:
    """BUG-36/60: Replace ``BREAK`` keyword and ``<break>`` tag with comma."""
    text = _BREAK_TAG_RE.sub(",", text)  # BUG-60: <break> tag first
    return _BREAK_RE.sub(",", text)


def strip_nai_bare_colons(text: str) -> str:
    """BUG-37: Replace bare ``::`` (no digit prefix) with comma."""
    return _BARE_COLON_RE.sub(",", text)


def strip_nai_brace_emphasis(text: str) -> str:
    """BUG-44: Unwrap ``{word}`` / ``{{word}}`` brace emphasis.

    Pipe-containing ``{a|b|c}`` (DP choices) are protected because the
    inner regex rejects ``|``.  Applied repeatedly to handle nested cases
    like ``hard {{brown}} nipple``.
    """
    prev = None
    while prev != text:
        prev = text
        text = _BRACE_EMPHASIS_RE.sub(r"\1", text)
    return text


def strip_wildcard_vars(text: str) -> str:
    """BUG-56: Remove ``${var}`` wildcard variable placeholders."""
    return _WILDCARD_VAR_RE.sub("", text)


def strip_angle_blocks(text: str) -> str:
    """BUG-33: Remove ``<lora:...>`` and similar angle-bracket blocks."""
    return _ANGLE_BLOCK_RE.sub("", text)


def normalize_adjacent_weights(text: str) -> str:
    """BUG-34: Insert comma between adjacent ``(tag:weight)`` groups."""
    return _ADJACENT_WEIGHT_RE.sub("), ", text)


def preprocess_prompt_text(text: str) -> str:
    """Run the full pre-processing pipeline (order is fixed).

    1. SD alternation removal
    2. BREAK keyword replacement
    3. Bare ``::`` removal
    4. NAI brace emphasis unwrap (repeated for nesting)
    5. Wildcard ``${var}`` removal
    6. Angle-bracket block removal
    7. Adjacent-weight normalisation
    """
    text = strip_sd_alternation(text)
    text = strip_break_keyword(text)
    text = strip_nai_bare_colons(text)
    text = strip_nai_brace_emphasis(text)
    text = strip_wildcard_vars(text)
    text = strip_angle_blocks(text)
    text = normalize_adjacent_weights(text)
    return text
