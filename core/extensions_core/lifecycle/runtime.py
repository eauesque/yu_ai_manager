"""Extension system runtime exports."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.extensions_core.extensions_defs import (
    HOOK_DEFINITIONS,
    DetailSection,
    ExtensionManifest,
    ExtractedMetadata,
    FilterExpr,
    validate_cli_gui_parity,
)

from .extensions_manager import ExtensionManager

_manager: ExtensionManager | None = None


def get_extension_manager() -> ExtensionManager:
    global _manager
    if _manager is None:
        _manager = ExtensionManager()
    return _manager


def init_extensions(extensions_dir: Path | None = None) -> ExtensionManager:
    global _manager
    _manager = ExtensionManager(extensions_dir)
    count = _manager.discover_and_load()
    if count > 0:
        logger.info(f"[Extension] {count} extension(s) loaded")
    return _manager


__all__ = [
    "HOOK_DEFINITIONS",
    "DetailSection",
    "ExtensionManifest",
    "ExtractedMetadata",
    "FilterExpr",
    "validate_cli_gui_parity",
    "ExtensionManager",
    "get_extension_manager",
    "init_extensions",
]
