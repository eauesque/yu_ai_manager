"""Tag post-processing: normalization and NSFW filtering.

Phase 3: normalize tags (lowercase, underscore, dedup) and optionally
remove NSFW tags based on a curated blocklist.
"""

from __future__ import annotations

import re

from .types import TagPrediction, WdTagResult

# Characters to strip from tags
_INVALID_CHARS = re.compile(r'[\[\](){}\"\'/\\]')
_MAX_TAG_LEN = 100

# Basic NSFW tag set (~30 tags covering common explicit content tags)
NSFW_TAG_SET: frozenset[str] = frozenset({
    "sex", "nude", "naked", "nipples", "nipple", "pussy", "penis",
    "vaginal", "anal", "cum", "cum_on_body", "cum_in_pussy",
    "cum_on_face", "cum_in_mouth", "fellatio", "oral", "paizuri",
    "handjob", "masturbation", "spread_legs", "spread_pussy",
    "ass_visible_through_thighs", "anus", "pubic_hair",
    "completely_nude", "topless", "bottomless", "censored",
    "uncensored", "mosaic_censoring", "bar_censor",
})


class TagPostProcessor:
    """Normalize and filter WD-Tagger results."""

    def normalize_tags(self, tags: list[TagPrediction]) -> list[TagPrediction]:
        """Normalize tag names: lowercase, underscore, dedup, length check."""
        seen: set[str] = set()
        result: list[TagPrediction] = []
        for tp in tags:
            name = tp.tag.strip().lower().replace(" ", "_")
            name = _INVALID_CHARS.sub("", name)
            if not (1 <= len(name) <= _MAX_TAG_LEN):
                continue
            if name in seen:
                continue
            seen.add(name)
            if name != tp.tag:
                tp = TagPrediction(tag=name, confidence=tp.confidence, category=tp.category)
            result.append(tp)
        return result

    def filter_nsfw(
        self,
        tags: list[TagPrediction],
        rating: str,
        allow_nsfw: bool,
    ) -> list[TagPrediction]:
        """Remove NSFW tags when filtering is enabled.

        Args:
            tags: List of tag predictions
            rating: Image rating (general/sensitive/questionable/explicit)
            allow_nsfw: If True, return tags as-is (no filtering)
        """
        if allow_nsfw:
            return tags
        return [t for t in tags if t.tag not in NSFW_TAG_SET]

    def process(self, result: WdTagResult, allow_nsfw: bool) -> WdTagResult:
        """Run full post-processing pipeline: normalize then filter."""
        tags = self.normalize_tags(result.tags)
        tags = self.filter_nsfw(tags, result.rating, allow_nsfw)
        return WdTagResult(tags=tags, model=result.model, rating=result.rating)
