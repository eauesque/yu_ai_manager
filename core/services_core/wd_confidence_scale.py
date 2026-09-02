"""Scale WD tag confidence between external float and DB integer storage."""

from __future__ import annotations

WD_CONFIDENCE_SCALE = 1000


def confidence_to_milli(confidence: float) -> int:
    value = int(round(float(confidence) * WD_CONFIDENCE_SCALE))
    return max(0, min(WD_CONFIDENCE_SCALE, value))


def confidence_from_milli(confidence_milli: int) -> float:
    return int(confidence_milli) / WD_CONFIDENCE_SCALE
