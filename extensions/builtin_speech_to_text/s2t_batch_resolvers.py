"""Facade for Speech-to-Text batch input resolution and execution."""

_EXT_NAME = "builtin-speech-to-text"
from .s2t_batch_inputs import resolve_directory, resolve_list_file
from .s2t_batch_worker import run_batch


def get_default_language() -> str:
    """Return the default language from extension config."""
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
    return get_extension_config_value(_EXT_NAME, "default_language", "ja")


__all__ = [
    "get_default_language",
    "resolve_directory",
    "resolve_list_file",
    "run_batch",
]
