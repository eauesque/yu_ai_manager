"""File, path, and annotation validators for MCP tools."""


from .validators_common import (
    ANNOTATION_SOURCE_KEY_MAX,
    ANNOTATION_VALUE_MAX,
    VALID_DUPLICATE_METHODS,
    VALID_HASH_TYPES,
    err,
)


def validate_file_id(file_id: int) -> str | None:
    if file_id <= 0:
        return err(f"Invalid file_id: {file_id} (must be positive integer)")
    return None


def validate_annotation_items(items: list) -> str | None:
    for index, item in enumerate(items):
        source = item.get("source", "")
        key = item.get("key", "")
        value = item.get("value", "")
        if len(str(source)) > ANNOTATION_SOURCE_KEY_MAX:
            return err(f"items[{index}].source too long ({len(str(source))} > {ANNOTATION_SOURCE_KEY_MAX})")
        if len(str(key)) > ANNOTATION_SOURCE_KEY_MAX:
            return err(f"items[{index}].key too long ({len(str(key))} > {ANNOTATION_SOURCE_KEY_MAX})")
        if len(str(value)) > ANNOTATION_VALUE_MAX:
            return err(f"items[{index}].value too long ({len(str(value))} > {ANNOTATION_VALUE_MAX})")
    return None


def validate_path(path: str) -> str | None:
    if not path or not path.strip():
        return err("path is required (non-empty string)")
    return None


def validate_hash_type(hash_type: str) -> str | None:
    if hash_type and hash_type not in VALID_HASH_TYPES:
        return err(f"Invalid hash_type: '{hash_type}'. Valid options: {', '.join(sorted(VALID_HASH_TYPES))}")
    return None


def validate_duplicate_method(method: str) -> str | None:
    if method and method not in VALID_DUPLICATE_METHODS:
        return err(f"Invalid method: '{method}'. Valid options: {', '.join(sorted(VALID_DUPLICATE_METHODS))}")
    return None
