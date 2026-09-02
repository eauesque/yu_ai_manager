"""Canonical path validation shared by update review, verification, and apply."""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

_WINDOWS_RESERVED_STEMS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class UnsafeUpdatePath(ValueError):
    """Raised when an update path has unsafe or platform-ambiguous syntax."""


def normalize_update_path(value: str) -> str:
    """Return one validated POSIX relative path, preserving display case."""
    if "\x00" in value or "\\" in value or value.startswith("/"):
        raise UnsafeUpdatePath(f"Unsafe relative path: {value}")
    normalized = posixpath.normpath(value)
    parts = PurePosixPath(normalized).parts
    if normalized in {"", "."} or normalized.startswith("../") or ".." in parts:
        raise UnsafeUpdatePath(f"Unsafe relative path: {value}")
    if normalized != value:
        raise UnsafeUpdatePath(f"Non-canonical relative path: {value}")
    for component in parts:
        if component.endswith((".", " ")) or ":" in component:
            raise UnsafeUpdatePath(f"Windows-ambiguous relative path: {value}")
        stem = component.split(".", 1)[0].rstrip(" .").casefold()
        if stem in _WINDOWS_RESERVED_STEMS:
            raise UnsafeUpdatePath(f"Windows-reserved relative path: {value}")
    return "/".join(parts)


def update_path_key(value: str) -> str:
    """Return the universal case-insensitive identity for an update path."""
    return normalize_update_path(value).casefold()
