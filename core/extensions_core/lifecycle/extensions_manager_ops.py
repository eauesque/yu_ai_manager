"""ExtensionManager ops compatibility facade."""

from .extensions_manager_lifecycle import (
    discover_and_load_extensions,
    load_single_extension,
    set_extension_enabled,
    unload_extension,
)
from .extensions_manager_register import register_blueprint, register_hooks

__all__ = [
    "discover_and_load_extensions",
    "load_single_extension",
    "register_blueprint",
    "register_hooks",
    "set_extension_enabled",
    "unload_extension",
]
