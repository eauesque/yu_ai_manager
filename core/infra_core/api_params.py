"""Query parameter normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# SQLite bind parameters overflow past the signed-64 boundary; clamp all
# integer inputs to this range before they reach a query parameter.
SQLITE_MIN_INT = -(2**63)
SQLITE_MAX_INT = 2**63 - 1


def clamp_sqlite_int(value: int) -> int:
    """Clamp an int into SQLite's signed-64-bit range so bind params never overflow."""
    return max(SQLITE_MIN_INT, min(SQLITE_MAX_INT, value))


def get_arg(args: Any, names: Iterable[str], default: Any = None) -> Any:
    """Return the first existing arg value among aliases."""
    for name in names:
        value = args.get(name)
        if value is not None:
            return value
    return default


def get_str_arg(args: Any, names: Iterable[str], default: str = "") -> str:
    value = get_arg(args, names, default)
    if value is None:
        return default
    # NUL terminates SQLite/FTS5's C strings mid-query and can surface as
    # "unterminated string"; HTTP query args have no legitimate NUL meaning.
    return str(value).replace("\x00", "").strip()


def get_int_arg(
    args: Any,
    names: Iterable[str],
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = get_arg(args, names, None)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    value = clamp_sqlite_int(value)
    return value


def get_bool_arg(args: Any, names: Iterable[str], default: bool = False) -> bool:
    raw = get_arg(args, names, None)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
