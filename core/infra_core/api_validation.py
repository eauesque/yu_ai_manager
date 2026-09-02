"""Shared validation helpers for API payloads."""

from __future__ import annotations

from typing import Any


def error_payload(message: str, code: str, status: int = 400):
    return {"error": message, "code": code}, status


def validate_index(index: int, length: int) -> tuple[dict, int] | None:
    if index < 0 or index >= length:
        return error_payload("Invalid index", "invalid_index", 400)
    return None


def validate_non_empty_str(value: Any, *, code: str, message: str) -> tuple[str, tuple[dict, int] | None]:
    text = str(value or "").strip()
    if not text:
        return "", error_payload(message, code, 400)
    return text, None
