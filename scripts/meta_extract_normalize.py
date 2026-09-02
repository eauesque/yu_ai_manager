"""Metadata-specific normalization for Python<->Rust conformance golden comparison."""
from __future__ import annotations

import json
import re
from typing import Any


def normalize_raw_meta(raw_meta: str | None) -> str | None:
    """Canonical-sort keys in embedded JSON; return None if absent/invalid."""
    if raw_meta is None:
        return None
    try:
        obj = json.loads(raw_meta)
    except (json.JSONDecodeError, ValueError):
        return raw_meta
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize_negative(negative: str | None) -> str | None:
    """Normalize join separators, strip trailing/leading whitespace and blank lines."""
    if negative is None:
        return None
    s = re.sub(r"\r\n|\r", "\n", negative)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def normalize_positive(positive: str | None) -> str | None:
    """Strip leading/trailing whitespace."""
    if positive is None:
        return None
    return positive.strip()


def normalize_fields(
    positive: str | None,
    negative: str | None,
    raw_meta: str | None,
) -> dict[str, Any]:
    """Return normalized dict of the three compared fields."""
    return {
        "positive": normalize_positive(positive),
        "negative": normalize_negative(negative),
        "raw_meta": normalize_raw_meta(raw_meta),
    }
