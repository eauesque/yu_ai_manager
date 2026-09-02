"""Merge WD-Tagger results from multiple video keyframes.

Pure functions for aggregating tag predictions across frames.
"""

from __future__ import annotations

from core.files_core.tagger_types import TagPrediction, WdTagResult


def merge_wd_tag_results(results: list[WdTagResult]) -> WdTagResult:
    """Merge multiple WD-Tagger results into one (union + max confidence).

    For tags: each unique (tag, category) pair keeps the highest confidence
    seen across all frames.

    For rating: adopts the rating from the frame with the highest confidence
    rating prediction.

    Args:
        results: List of WdTagResult from individual keyframes.

    Returns:
        A single merged WdTagResult. Returns empty result if input is empty.
    """
    if not results:
        return WdTagResult()
    if len(results) == 1:
        return results[0]

    model = results[0].model

    # Merge tags: (tag_name, category) -> max confidence
    tag_map: dict[tuple, float] = {}
    for r in results:
        for t in r.tags:
            key = (t.tag, t.category)
            if key not in tag_map or t.confidence > tag_map[key]:
                tag_map[key] = t.confidence

    merged_tags = [
        TagPrediction(tag=tag, confidence=conf, category=cat)
        for (tag, cat), conf in sorted(
            tag_map.items(), key=lambda x: x[1], reverse=True,
        )
    ]

    # Rating: pick from the frame with highest-confidence rating tag
    best_rating = results[0].rating
    best_rating_conf = -1.0
    for r in results:
        # Find the max confidence of any rating-category tag in this result
        rating_tags = [t for t in r.tags if t.category == "rating"]
        if rating_tags:
            max_conf = max(t.confidence for t in rating_tags)
            if max_conf > best_rating_conf:
                best_rating_conf = max_conf
                best_rating = r.rating

    return WdTagResult(tags=merged_tags, model=model, rating=best_rating)
