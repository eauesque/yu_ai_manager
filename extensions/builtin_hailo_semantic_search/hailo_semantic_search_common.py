"""Shared helpers for Hailo semantic search routes."""

from core.extensions_core.extensions_admin import get_extension_config_value

EXT_NAME = "builtin-hailo-semantic-search"


def ext_config(key: str, default):
    return get_extension_config_value(EXT_NAME, key, default)
