"""ThresholdTable — schema v2 threshold resolver (2 種).

Spec § 5.3 / § 6. global_per_category と per_tag_json の 2 形式を扱う。
UI override は per_tag を含めて完全置換 (additive ではなく replace)。
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from .base import TaggerProfile
from .tag_source import MetadataLoadError, _read_json_bounded  # reuse bounded reader

logger = logging.getLogger(__name__)

_MAX_PER_TAG_ENTRIES = 100_000  # spec § 5.6


class ThresholdTable:
    """Resolved threshold lookup for one profile."""

    def __init__(
        self,
        *,
        per_tag: dict[str, float] | None,
        default_thresholds: dict[str, float],
        fallback_mode: str,
        fallback_value: float,
    ):
        self._per_tag = per_tag  # None = global_per_category mode
        self._defaults = dict(default_thresholds)
        self._fallback_mode = fallback_mode
        self._fallback_value = fallback_value

    @classmethod
    def from_profile(
        cls,
        profile: TaggerProfile,
        model_dir: Path,
    ) -> ThresholdTable:
        ths = profile.threshold_source
        ths_type = ths.get("type")

        if ths_type == "global_per_category":
            return cls(
                per_tag=None,
                default_thresholds=dict(profile.default_thresholds),
                fallback_mode="category_default",
                fallback_value=float(
                    profile.default_thresholds.get("general", 0.35)
                ),
            )

        if ths_type == "per_tag_json":
            raw = _read_json_bounded(model_dir / ths["file"], ctx="threshold_source.file")
            if not isinstance(raw, dict):
                raise MetadataLoadError(
                    f"threshold_source.file must be dict: got {type(raw).__name__}"
                )
            if len(raw) > _MAX_PER_TAG_ENTRIES:
                raise MetadataLoadError(
                    f"threshold_source.file {ths['file']!r} has {len(raw)} entries "
                    f"exceeding cap {_MAX_PER_TAG_ENTRIES}"
                )
            per_tag: dict[str, float] = {}
            for k, v in raw.items():
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise MetadataLoadError(
                        f"threshold_source.file[{k!r}] not numeric: {v!r}"
                    )
                fv = float(v)
                if not math.isfinite(fv):
                    raise MetadataLoadError(
                        f"threshold_source.file[{k!r}]={v!r} not finite"
                    )
                if fv < 0.0 or fv > 1.0:
                    logger.warning(
                        "threshold_source.file[%r]=%r out of [0,1], clamping",
                        k, v,
                    )
                    fv = max(0.0, min(1.0, fv))
                per_tag[str(k)] = fv

            fb = ths.get("fallback") or {}
            fb_mode = str(fb.get("mode", "global"))
            fb_value_raw = fb.get("value", 0.35)
            if isinstance(fb_value_raw, bool) or not isinstance(fb_value_raw, (int, float)):
                raise MetadataLoadError(
                    f"threshold_source.fallback.value must be numeric: {fb_value_raw!r}"
                )
            fb_value = float(fb_value_raw)
            if not math.isfinite(fb_value):
                raise MetadataLoadError(
                    f"threshold_source.fallback.value not finite: {fb_value_raw!r}"
                )
            if fb_value < 0.0 or fb_value > 1.0:
                logger.warning(
                    "threshold_source.fallback.value=%r out of [0,1], clamping",
                    fb_value_raw,
                )
                fb_value = max(0.0, min(1.0, fb_value))
            if fb_mode not in ("global", "category_default"):
                raise MetadataLoadError(
                    f"threshold_source.fallback.mode={fb_mode!r} not in global/category_default"
                )
            return cls(
                per_tag=per_tag,
                default_thresholds=dict(profile.default_thresholds),
                fallback_mode=fb_mode,
                fallback_value=fb_value,
            )

        raise MetadataLoadError(f"threshold_source.type={ths_type!r} not supported")

    def for_tag(
        self,
        tag: str,
        category: str,
        *,
        ui_override: float | None = None,
    ) -> float:
        if ui_override is not None:
            return float(ui_override)
        if self._per_tag is None:
            # global_per_category mode
            return float(
                self._defaults.get(category, self._defaults.get("general", 0.35))
            )
        # per_tag_json mode
        if tag in self._per_tag:
            return self._per_tag[tag]
        if self._fallback_mode == "category_default":
            return float(
                self._defaults.get(category, self._defaults.get("general", self._fallback_value))
            )
        return self._fallback_value
