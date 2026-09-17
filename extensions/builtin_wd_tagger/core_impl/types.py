"""Type definitions for WD-Tagger module.

Phase 1b: WdTagResult is now an alias for the new TagResult in
adapters.base (same shape + `model` property for legacy `.model` reads
+ `model=` kwarg constructor support for legacy callers that build
results positionally — see TagResult.__init__ in adapters.base).
WdTaggerEngine ABC is preserved for legacy engine classes
(OnnxWdTaggerEngine, VlmWdTaggerEngine, CompositeWdTaggerEngine) which
have their own get_name() etc. New code should use TaggerAdapter.
"""

from __future__ import annotations

import abc

# Re-export new types as the legacy names. WdTagResult is the same object
# as the new TagResult; legacy callers that read `.model` get the property
# defined on TagResult (which aliases model_id).
from .adapters.base import TagPrediction, TagResult

WdTagResult = TagResult

__all__ = ["TagPrediction", "WdTagResult", "WdTaggerEngine"]


class WdTaggerEngine(abc.ABC):
    """Legacy abstract base class for WD-Tagger inference engines.

    Kept for backward compat with engine_onnx.OnnxWdTaggerEngine,
    engine_vlm.VlmWdTaggerEngine, and engine_composite.CompositeWdTaggerEngine.
    New code should subclass adapters.base.TaggerAdapter instead.
    """

    @abc.abstractmethod
    def tag_image(self, image_path: str) -> WdTagResult:
        """Run inference on a single image and return predicted tags."""

    def tag_images_batch(
        self, filepaths: list[str], batch_size: int = 8,
    ) -> list:
        """Default sequential fallback. ONNX engine overrides for batched inference."""
        results: list = []
        for fp in filepaths:
            try:
                results.append(self.tag_image(fp))
            except Exception:
                results.append(None)
        return results

    @abc.abstractmethod
    def get_name(self) -> str:
        """Human-readable engine name."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if the engine is ready (model loaded, etc.)."""
