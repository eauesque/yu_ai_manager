"""Protect/restore escaped brackets during SD/NAI conversion.

Escaped brackets like ``\\(literal\\)`` must pass through conversion
unchanged.  The protect-process-restore pattern replaces them with
null-byte placeholders before any regex processing and restores them
afterwards.
"""

from __future__ import annotations

_ESC_TOKENS = ("\\(", "\\)", "\\[", "\\]", "\\{", "\\}")


def protect_escapes(text: str) -> tuple[str, list[str]]:
    """Replace escaped brackets with ``\\x00E{i}\\x00`` placeholders."""
    saved: list[str] = []
    for esc in _ESC_TOKENS:
        while esc in text:
            saved.append(esc)
            text = text.replace(esc, f"\x00E{len(saved) - 1}\x00", 1)
    return text, saved


def restore_escapes(text: str, saved: list[str]) -> str:
    """Restore placeholders back to original escaped brackets."""
    for i, s in enumerate(saved):
        text = text.replace(f"\x00E{i}\x00", s)
    return text
