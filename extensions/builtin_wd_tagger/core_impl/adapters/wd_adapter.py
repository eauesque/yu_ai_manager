"""WD adapter family — SmilingWolf/wd-* tagger models.

Spec § 4.1 (adapters/wd_adapter.py), § 5.4 (preprocess_spec).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..backends.base import BackendSession
from .base import TaggerAdapter, TaggerProfile, TagPrediction, TagResult
from .preprocess import preprocess_image_from_spec

logger = logging.getLogger(__name__)


class WdAdapter(TaggerAdapter):
    """Adapter for SmilingWolf/wd-* family tagger models."""

    def __init__(
        self,
        profile: TaggerProfile,
        backend: BackendSession,
        csv_path: str | Path,
        thresholds: dict[str, float],
    ):
        self._profile = profile
        self._backend = backend
        self._csv_path = Path(csv_path)
        self._thresholds = dict(thresholds)
        self._tag_names: list[str] = []
        self._categories: list[str] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        from .tag_source import load_tag_source
        pairs = load_tag_source(self._profile, self._csv_path.parent)
        self._tag_names = [t for t, _ in pairs]
        self._categories = [c for _, c in pairs]
        self._loaded = True
        logger.info(
            "WdAdapter ready: profile=%s tags=%d",
            self._profile.id, len(self._tag_names),
        )

    def _build_result(self, probs: np.ndarray) -> TagResult:
        """Build a TagResult from a model output probability vector."""
        general_thr = float(self._thresholds.get("general", 0.35))
        character_thr = float(self._thresholds.get("character", 0.85))

        # Match legacy OnnxWdTaggerEngine: initialize rating_max to 0.0 so a
        # rating tag with conf == 0.0 keeps the default "general" label.
        rating_label = "general"
        rating_max = 0.0
        tags: list[TagPrediction] = []

        for i, (name, category) in enumerate(zip(
            self._tag_names, self._categories, strict=False,
        )):
            if i >= len(probs):
                break
            conf = float(probs[i])

            if category == "rating":
                if conf > rating_max:
                    rating_max = conf
                    rating_label = name
                continue

            threshold = character_thr if category == "character" else general_thr
            if conf >= threshold:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=round(conf, 4),
                    category=category,
                ))

        tags.sort(key=lambda t: t.confidence, reverse=True)

        return TagResult(
            tags=tags,
            model_id=self._profile.id,
            rating=rating_label,
        )

    def tag_image(self, image_path: str) -> TagResult:
        self._ensure_loaded()
        input_arr = preprocess_image_from_spec(
            image_path, self._profile.preprocess_spec,
        )
        output = self._backend.run(input_arr)
        # output shape: (1, num_tags)
        probs = output[0]
        return self._build_result(probs)

    def get_profile(self) -> TaggerProfile:
        return self._profile

    def is_available(self) -> bool:
        return self._backend.is_loaded() and self._csv_path.exists()
