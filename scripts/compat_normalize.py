"""Shared response normalization for Rust/Python compatibility checks."""

from __future__ import annotations

from typing import Any

VOLATILE_KEYS = {
    "timestamp",
    "uptime",
    "now",
    "elapsed",
    "ts",
    "time",
    "date",
    "version",
    "last_synced",
    "generated_at",
}
VOLATILE_VALUE = "<volatile>"


def normalize_json_body(value: Any) -> Any:
    """Replace volatile JSON fields at any depth."""
    if isinstance(value, dict):
        return {
            key: VOLATILE_VALUE if key in VOLATILE_KEYS else normalize_json_body(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_json_body(item) for item in value]
    return value


def normalize_content_type(content_type: str) -> str:
    """Drop content-type parameters that vary by framework."""
    return content_type.split(";", 1)[0].strip().lower()
