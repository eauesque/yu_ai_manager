"""Lightweight fuzzy matching without external dependencies."""

from __future__ import annotations


def edit_distance(s1: str, s2: str, max_dist: int = 2) -> int:
    """Levenshtein distance (with early termination).

    Returns max_dist + 1 if the distance exceeds max_dist.
    """
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > max_dist:
        return max_dist + 1

    prev = list(range(len2 + 1))
    for i in range(1, len1 + 1):
        curr = [i] + [0] * len2
        row_min = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > max_dist:
            return max_dist + 1
        prev = curr

    return prev[len2]


def fuzzy_filter(
    query: str,
    candidates: list[dict],
    threshold: int = 2,
) -> list[dict]:
    """Extract candidates with distance <= threshold and sort them."""
    q = query.lower()
    results: list[tuple[int, dict]] = []
    for cand in candidates:
        tag = cand["tag_name"].lower()
        dist = edit_distance(q, tag, threshold)
        if dist <= threshold:
            results.append((dist, cand))

    results.sort(key=lambda x: (x[0], -x[1].get("post_count", 0)))
    return [r[1] for r in results]
