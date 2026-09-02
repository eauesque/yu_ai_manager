"""Composite engine: ONNX + VLM two-stage tagging (Mode B).

Stage 1: Run ONNX inference for high-precision base tags.
Stage 2: Send high-confidence tags to VLM for complementary suggestions.
Merge both results with deduplication.
"""

from __future__ import annotations

import logging

from .types import TagPrediction, WdTaggerEngine, WdTagResult

logger = logging.getLogger(__name__)

# ONNX tags with confidence >= this threshold are sent to VLM as context
_HIGH_CONFIDENCE_THRESHOLD = 0.7


class CompositeWdTaggerEngine(WdTaggerEngine):
    """ONNX + VLM composite engine (Mode B)."""

    def __init__(
        self,
        onnx_engine: WdTaggerEngine,
        vlm_engine: VlmWdTaggerEngine,  # noqa: F821
    ):
        self._onnx = onnx_engine
        self._vlm = vlm_engine

    def tag_image(self, image_path: str) -> WdTagResult:
        # Stage 1: ONNX base tags
        onnx_result = self._onnx.tag_image(image_path)

        # Extract high-confidence tags as context for VLM
        high_conf_tags = [
            t.tag for t in onnx_result.tags
            if t.confidence >= _HIGH_CONFIDENCE_THRESHOLD
        ]

        # Stage 2: VLM complement
        vlm_tags: list[TagPrediction] = []
        if high_conf_tags:
            try:
                vlm_tags = self._vlm.request_complement(image_path, high_conf_tags)
            except Exception as exc:
                logger.warning("VLM complement failed, using ONNX only: %s", exc)

        # Merge: ONNX tags + VLM complement (dedup by tag name)
        seen = {t.tag for t in onnx_result.tags}
        merged = list(onnx_result.tags)
        for vt in vlm_tags:
            if vt.tag not in seen:
                seen.add(vt.tag)
                merged.append(vt)

        model_name = f"{self._onnx.get_name()} + {self._vlm.get_name()}"
        return WdTagResult(tags=merged, model=model_name, rating=onnx_result.rating)

    def get_name(self) -> str:
        return f"Composite ({self._onnx.get_name()} + {self._vlm.get_name()})"

    def is_available(self) -> bool:
        return self._onnx.is_available() and self._vlm.is_available()
