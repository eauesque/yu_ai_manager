"""VLM adapter shim (Phase 1b).

Wraps the legacy ``engine_vlm.VlmWdTaggerEngine`` so that VLM-based tagging
flows through the new TaggerAdapter framework. A synthetic TaggerProfile is
built from the VLM config (vlm_url / vlm_model / vlm_timeout); profile
validation constraints are satisfied by sanitizing special characters into the
allowed regex set.

In Phase 3 this shim will be replaced by a proper VlmAdapter that owns its
inference path (without going through legacy engine_vlm).

Spec § 3.2 item 2 / § 4.1 (adapters/vlm_adapter.py).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .base import (
    TaggerAdapter,
    TaggerProfile,
    TagPrediction,
    TagResult,
)

_INVALID_MODEL_ID_CHAR = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_for_model_id(name: str) -> str:
    sanitized = _INVALID_MODEL_ID_CHAR.sub("_", name).strip("._-")
    while ".." in sanitized:
        sanitized = sanitized.replace("..", "__")
    if not sanitized or not sanitized[0].isalnum():
        return f"x_{sanitized}"
    return sanitized


def build_vlm_profile(
    base_url: str,
    model_name: str,
    timeout: int = 60,
) -> TaggerProfile:
    """Build a synthetic TaggerProfile for a VLM endpoint.

    The profile id is deterministic per ``(base_url, model_name, timeout)`` so
    that EngineCache hits for the same VLM config.
    """
    sanitized_model = _sanitize_for_model_id(model_name)
    digest = hashlib.sha256(f"{base_url}|{model_name}|{timeout}".encode()).hexdigest()[:8]

    return TaggerProfile.from_dict({
        "profile_version": "2",
        "id": f"vlm_{sanitized_model}_{digest}",
        "display_name": f"VLM ({model_name})",
        "model_id": f"vlm_local/{sanitized_model}",
        "adapter_family": "vlm",
        "backend": "vlm",
        "builtin": False,
        # VLM doesn't use a real tag file; declare a marker file so the
        # schema-v2 cross-check (§ 5.6) sees tag_source.file in files[]
        # with required=true. The runtime VLM adapter never opens it.
        "files": [{"name": "vlm.txt", "required": True, "size_hint_mb": 0.0}],
        "preprocess_spec": {
            # VLM bypasses image preprocessing entirely; values below are
            # validation-safe placeholders to satisfy schema v2 numeric/enum
            # checks (spec § 5.6). The runtime VLM adapter ignores these
            # fields and forwards raw image bytes to the upstream API.
            "input_size": 32,
            "resize_strategy": "longest_side_pad",
            "pad_color": [255, 255, 255],
            "channel_order": "RGB",
            "dtype": "float32",
            "scale": 1.0,
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
            "layout": "NHWC",
            "vlm_base_url": base_url,
            "vlm_model": model_name,
            "vlm_timeout": timeout,
        },
        "tag_source": {
            "type": "json_list",
            "file": "vlm.txt",
        },
        "threshold_source": {"type": "global_per_category"},
        "categories_mode": "all_general",
        "default_thresholds": {"general": 0.0},
        "supports_categories": ["general"],
    })


class VlmAdapter(TaggerAdapter):
    """Phase 1b shim: wraps legacy VlmWdTaggerEngine via composition."""

    def __init__(self, profile: TaggerProfile, legacy_engine: Any | None = None):
        self._profile = profile
        if legacy_engine is None:
            from ..engine_vlm import VlmWdTaggerEngine

            legacy_engine = VlmWdTaggerEngine(
                base_url=str(profile.preprocess_spec.get("vlm_base_url", "")),
                model=str(profile.preprocess_spec.get("vlm_model", "")),
                timeout=int(profile.preprocess_spec.get("vlm_timeout", 60)),
            )
        self._legacy = legacy_engine

    def tag_image(self, image_path: str) -> TagResult:
        legacy_result = self._legacy.tag_image(image_path)
        tags = [
            TagPrediction(
                tag=t.tag,
                confidence=t.confidence,
                category=t.category,
            )
            for t in legacy_result.tags
        ]
        return TagResult(
            tags=tags,
            model_id=self._profile.id,
            rating=getattr(legacy_result, "rating", ""),
        )

    def get_profile(self) -> TaggerProfile:
        return self._profile

    def is_available(self) -> bool:
        return bool(self._legacy.is_available())
