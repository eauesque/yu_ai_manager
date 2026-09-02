"""Generic ONNX adapter - data-driven, profile-based.

Unlike WdAdapter (which assumes WD-specific category constants like
'general'/'character'/'rating'), GenericOnnxAdapter treats every category
listed in ``profile.tag_source["category_map"].values()`` as first-class
and looks up a per-category threshold from ``thresholds`` (or falls back
to ``thresholds["general"]`` for unmapped categories).

Spec § 4.1 (adapters/generic_onnx_adapter.py).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..backends.base import BackendSession
from .base import TaggerAdapter, TaggerProfile, TagPrediction, TagResult
from .preprocess import preprocess_image_from_spec
from .tag_source import load_tag_source
from .threshold import ThresholdTable

logger = logging.getLogger(__name__)


class GenericOnnxAdapter(TaggerAdapter):
    """Data-driven ONNX adapter for any profile whose preprocess_spec /
    tag_csv_spec fully describes the model."""

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
        # Kept for backward compat (legacy callers may inspect it);
        # actual per-tag threshold lookup goes through self._threshold_table.
        # Will be removed once Phase 5 threshold-override UI lands.
        self._thresholds = dict(thresholds)
        self._tag_names: list[str] = []
        self._categories: list[str] = []
        self._threshold_table: ThresholdTable | None = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        model_dir = self._csv_path.parent
        pairs = load_tag_source(self._profile, model_dir)
        self._tag_names = [t for t, _ in pairs]
        self._categories = [c for _, c in pairs]
        self._threshold_table = ThresholdTable.from_profile(
            self._profile, model_dir,
        )
        self._loaded = True
        logger.info(
            "%s ready: profile=%s tags=%d",
            type(self).__name__, self._profile.id, len(self._tag_names),
        )

    def _build_result(self, probs: np.ndarray) -> TagResult:
        """Build a TagResult from a model output probability vector."""
        rating_label = "general"
        rating_max = 0.0
        tags: list[TagPrediction] = []
        assert self._threshold_table is not None  # _ensure_loaded guarantees this

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

            threshold = self._threshold_table.for_tag(name, category)
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
        spec = self._profile.output_spec
        output = self._backend.run(input_arr, spec.get("output_key"))
        # output shape: (1, num_tags) for NHWC or NCHW input - both
        # produce a flat per-tag vector at the output head.
        probs = output[0]
        if spec.get("activation") == "sigmoid":
            # The exported graph stops at the logits; thresholds in the
            # profile are probabilities, so comparing them against logits
            # silently rescales every threshold.
            probs = 1.0 / (1.0 + np.exp(-probs.astype(np.float64)))
        return self._build_result(probs)

    def get_profile(self) -> TaggerProfile:
        return self._profile

    def is_available(self) -> bool:
        return self._backend.is_loaded() and self._csv_path.exists()
