"""Extension system constants/types compatibility facade."""

from core.extensions_core.extensions_defs_constants import (
    CATEGORY_ORDER,
    HOOK_DEFINITIONS,
    MANIFEST_NAMES_JSON,
    MANIFEST_NAMES_YAML,
    META_ARGS,
    VALID_CAPABILITIES,
    VALID_CATEGORIES,
    VALID_PERMISSIONS,
    VALID_TYPES,
)
from core.extensions_core.extensions_defs_models import (
    ConfigField,
    DetailSection,
    ExtensionManifest,
    ExtractedMetadata,
    FilterExpr,
    HookEntry,
    PermissionDecl,
    PermissionSet,
    TrustLevel,
)
from core.extensions_core.extensions_defs_validation import validate_cli_gui_parity

__all__ = [
    "CATEGORY_ORDER",
    "ConfigField",
    "DetailSection",
    "ExtensionManifest",
    "ExtractedMetadata",
    "FilterExpr",
    "HOOK_DEFINITIONS",
    "HookEntry",
    "MANIFEST_NAMES_JSON",
    "MANIFEST_NAMES_YAML",
    "META_ARGS",
    "PermissionDecl",
    "PermissionSet",
    "TrustLevel",
    "VALID_CAPABILITIES",
    "VALID_CATEGORIES",
    "VALID_PERMISSIONS",
    "VALID_TYPES",
    "validate_cli_gui_parity",
]
