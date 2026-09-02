"""WD-Tagger type definitions (shared by core).

A lightweight copy that remains accessible from core modules such as
video_tag_merge even after wd_tagger_core has been moved to an extension.
Compatible with wd_tagger_core.types.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TagPrediction:
    """Single predicted tag with confidence and category."""

    tag: str
    confidence: float
    category: str = "general"


@dataclass
class WdTagResult:
    """Result of WD-Tagger inference on a single image."""

    tags: list[TagPrediction] = field(default_factory=list)
    model: str = ""
    rating: str = ""

    @property
    def general_tags(self) -> list[TagPrediction]:
        return [t for t in self.tags if t.category == "general"]

    @property
    def character_tags(self) -> list[TagPrediction]:
        return [t for t in self.tags if t.category == "character"]

    @property
    def copyright_tags(self) -> list[TagPrediction]:
        return [t for t in self.tags if t.category == "copyright"]

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "rating": self.rating,
            "tags": [
                {"tag": t.tag, "confidence": t.confidence, "category": t.category}
                for t in self.tags
            ],
            "count": len(self.tags),
        }
