"""Extension loader compatibility facade."""

from .extensions_loader_manifest import load_manifest, parse_config_schema
from .extensions_loader_module import load_extension_module

__all__ = ["load_extension_module", "load_manifest", "parse_config_schema"]
