"""Tag string normalization helpers."""

import logging
import re

logger = logging.getLogger(__name__)

# BUG-67: Minimum word-character requirement for valid tags (Unicode-aware)
_HAS_WORD_RE = re.compile(r"\w")


def normalize_tag_string(tag: str) -> str:
    normalized = tag.strip()
    if not normalized:
        return normalized

    if normalized.startswith("<") and normalized.endswith(">"):
        return normalized
    if normalized in ("BREAK", "AND"):
        return normalized

    normalized = re.sub(r"^[\d.]+::(.+?)(?:::)?$", r"\1", normalized)

    while len(normalized) >= 2:
        if (normalized[0] == "(" and normalized[-1] == ")") or (
            normalized[0] == "[" and normalized[-1] == "]"
        ) or (normalized[0] == "{" and normalized[-1] == "}"):
            normalized = normalized[1:-1].strip()
        else:
            break

    normalized = re.sub(r":[\d.]+$", "", normalized)
    normalized = re.sub(r":[\d.]+\)", "", normalized)

    open_count = normalized.count("(")
    close_count = normalized.count(")")
    if open_count != close_count:
        if close_count > open_count:
            excess = close_count - open_count
            for _ in range(excess):
                idx = normalized.rfind(")")
                if idx >= 0:
                    normalized = normalized[:idx] + normalized[idx + 1 :]
        if open_count > close_count:
            excess = open_count - close_count
            for _ in range(excess):
                idx = normalized.find("(")
                if idx >= 0:
                    normalized = normalized[:idx] + normalized[idx + 1 :]

    if "|" in normalized:
        parts = [p.strip() for p in normalized.split("|") if p.strip()]
        if len(parts) > 1:
            normalized = ", ".join(normalize_tag_string(p) for p in parts if p)
            return normalized
        if len(parts) == 1:
            normalized = parts[0]

    normalized = normalized.replace("\\(", "(").replace("\\)", ")")
    normalized = normalized.replace("\\[", "[").replace("\\]", "]")
    normalized = normalized.replace("\\{", "{").replace("\\}", "}")
    normalized = re.sub(r",(?!\s)", ", ", normalized)
    normalized = normalized.rstrip(".,;:!?")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip()
    # BUG-67: Re-strip trailing punctuation exposed after whitespace cleanup
    normalized = normalized.rstrip(".,;:!?")
    normalized = normalized.strip()
    try:
        from core.scan_core.scanner_hooks_tags import normalize_via_hooks
        normalized = normalize_via_hooks(normalized)
    except Exception:
        logger.warning("step failed", exc_info=True)
    return normalized


def split_normalized_tag(tag: str) -> list:
    normalized = normalize_tag_string(tag)
    if not normalized:
        return []
    # BUG-67: Skip tags with no word characters (symbol-only garbage)
    if not _HAS_WORD_RE.search(normalized):
        return []
    if ", " in normalized:
        return [t.strip() for t in normalized.split(", ")
                if t.strip() and _HAS_WORD_RE.search(t)]
    return [normalized]
