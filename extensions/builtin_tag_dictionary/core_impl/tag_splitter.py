"""Tag splitting helper for comma-less tags (DP-based)."""

from __future__ import annotations

import re
import threading

from .store import get_all_tag_names

_cache_lock = threading.Lock()
_tag_set: set[str] | None = None


def _get_tag_set() -> set[str]:
    """Get the set of dictionary tag names with caching."""
    global _tag_set
    if _tag_set is not None:
        return _tag_set
    with _cache_lock:
        if _tag_set is not None:
            return _tag_set
        _tag_set = get_all_tag_names(min_post_count=50)
    return _tag_set


def invalidate_cache() -> None:
    """Clear cache (call after import, etc.)."""
    global _tag_set
    with _cache_lock:
        _tag_set = None


def suggest_splits(text: str, max_suggestions: int = 5) -> list[dict]:
    """Return split candidates for text into dictionary tags.

    Uses DP to find longest-match-first, minimum-tag-count splits.
    Returns: [{"tags": [...], "coverage": float}]
    """
    normalized = re.sub(r"[\s_]+", "", text).lower()
    if not normalized:
        return []

    tag_set = _get_tag_set()
    if not tag_set:
        return []

    n = len(normalized)
    # Calculate max tag length in dictionary
    max_tag_len = max((len(t.replace("_", "")) for t in tag_set), default=0)
    if max_tag_len == 0:
        return []

    # DP: dp[i] = (min tag count, tag sequence) covering normalized[:i]
    dp: list[tuple[int, list[str]] | None] = [None] * (n + 1)
    dp[0] = (0, [])

    for i in range(n):
        if dp[i] is None:
            continue
        count_i, tags_i = dp[i]
        for end in range(i + 1, min(i + max_tag_len + 1, n + 1)):
            substr = normalized[i:end]
            # Check if exists in dictionary (compare without underscores)
            matched_tag = _find_tag(substr, tag_set)
            if matched_tag is None:
                continue
            new_count = count_i + 1
            if dp[end] is None or new_count < dp[end][0]:
                dp[end] = (new_count, tags_i + [matched_tag])

    if dp[n] is None:
        # Try best-effort if full coverage is not possible
        best_idx = 0
        for i in range(n, -1, -1):
            if dp[i] is not None:
                best_idx = i
                break
        if best_idx == 0:
            return []
        _, tags = dp[best_idx]
        coverage = best_idx / n
        return [{"tags": tags, "coverage": round(coverage, 3)}]

    _, tags = dp[n]
    result = {"tags": tags, "coverage": 1.0}
    return [result]


def _find_tag(substr: str, tag_set: set[str]) -> str | None:
    """Check if substr matches a tag in the dictionary."""
    # Direct match
    if substr in tag_set:
        return substr
    # Match with underscores (e.g. "blueeyes" -> "blue_eyes")
    # Dictionary stores tags with underscores, so
    # try possible underscore insertion positions in substr (short tags only)
    # For performance, look up dictionary directly
    for tag in tag_set:
        if tag.replace("_", "") == substr:
            return tag
    return None
