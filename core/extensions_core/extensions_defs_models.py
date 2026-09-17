"""Dataclasses for extension system (compatibility facade)."""

from core.extensions_core.extensions_defs_dataclasses import (
    ConfigField,
    DetailSection,
    ExtensionManifest,
    ExtractedMetadata,
    HookEntry,
    PermissionDecl,
    PermissionSet,
    TrustLevel,
)
from core.extensions_core.extensions_defs_filter_expr import FilterExpr

__all__ = [
    "ConfigField",
    "DetailSection",
    "ExtensionManifest",
    "ExtractedMetadata",
    "FilterExpr",
    "HookEntry",
    "PermissionDecl",
    "PermissionSet",
    "TrustLevel",
]
