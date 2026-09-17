"""Shared scalar type guards for gateway request validation."""

from __future__ import annotations

import math
from typing import Any


def is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(float(value))
    )


def is_integer(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)
