"""Tagger inference result types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TagPrediction:
    """Single predicted tag with confidence and category."""

    tag: str
    confidence: float
    category: str = "general"


class TagResult:
    """Result of one inference call."""

    def __init__(
        self,
        tags: list[TagPrediction] | None = None,
        model_id: str | None = None,
        rating: str = "",
        elapsed_ms: float = 0.0,
        *,
        model: str | None = None,
    ):
        if model_id is not None and model is not None and model_id != model:
            raise TypeError(f"TagResult got conflicting model_id={model_id!r} and model={model!r}")
        self.tags: list[TagPrediction] = list(tags) if tags is not None else []
        self.model_id: str = model_id if model_id is not None else (model or "")
        self.rating: str = rating
        self.elapsed_ms: float = elapsed_ms

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TagResult):
            return NotImplemented
        return (
            self.tags == other.tags
            and self.model_id == other.model_id
            and self.rating == other.rating
            and self.elapsed_ms == other.elapsed_ms
        )

    def __repr__(self) -> str:
        return (
            f"TagResult(tags={self.tags!r}, model_id={self.model_id!r}, "
            f"rating={self.rating!r}, elapsed_ms={self.elapsed_ms!r})"
        )

    @property
    def model(self) -> str:
        """Legacy alias for model_id."""
        return self.model_id

    @property
    def general_tags(self) -> list[TagPrediction]:
        return [tag for tag in self.tags if tag.category == "general"]

    @property
    def character_tags(self) -> list[TagPrediction]:
        return [tag for tag in self.tags if tag.category == "character"]

    @property
    def copyright_tags(self) -> list[TagPrediction]:
        return [tag for tag in self.tags if tag.category == "copyright"]

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "rating": self.rating,
            "elapsed_ms": self.elapsed_ms,
            "tags": [
                {"tag": tag.tag, "confidence": tag.confidence, "category": tag.category}
                for tag in self.tags
            ],
            "count": len(self.tags),
        }
