"""Shared validation helpers for WD-Tagger route handlers."""


def parse_bool_field(data: dict, key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def parse_int_field(
    data: dict,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value
