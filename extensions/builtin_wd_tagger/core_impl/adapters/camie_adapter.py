"""CamieAdapter - Camie Tagger family (ViT-base/16 backbone, 512px input).

Phase 2: thin subclass of GenericOnnxAdapter. Camie's metadata JSON
(camie-tagger-v2-metadata.json) is loaded via the json_dict mapping
sub-form (idx_to_tag + tag_to_category dicts under dataset_info.tag_mapping).
Categories: general / character / copyright / artist / meta / rating / year (7 cats, full Danbooru-style set).

Reasons to keep as a separate class:
  1. Spec § 4.1 / § 12 lists "Camie adapter" as a distinct entry, so
     the existence of the class makes the family registry symmetric
     with WD.
  2. Future Phase 3+ Camie-specific extensions (e.g. NSFW-aware
     threshold blending, custom tag aliasing) override methods on this
     subclass without touching GenericOnnxAdapter.

Currently no method overrides - Camie inference is fully expressed in
profiles/camie_tagger_v2.json via the json_dict mapping sub-form.
"""
from __future__ import annotations

from .generic_onnx_adapter import GenericOnnxAdapter


class CamieAdapter(GenericOnnxAdapter):
    """Camie family adapter (currently delegates entirely to base)."""
