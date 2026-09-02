"""Core dataclasses for extension system."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class TrustLevel(StrEnum):
    """Trust level for extensions."""
    TRUSTED = "trusted"        # L0: builtin-* — no restrictions
    VERIFIED = "verified"      # L1: signature verified — declared permissions only (Phase 2)
    UNTRUSTED = "untrusted"    # L2: unverified — user approval required


@dataclass
class PermissionDecl:
    """Permission declaration. name must be one of VALID_PERMISSIONS."""
    name: str
    reason: str = ""


@dataclass
class PermissionSet:
    """Permission set requested by an extension."""
    required: list[PermissionDecl] = field(default_factory=list)
    optional: list[PermissionDecl] = field(default_factory=list)


@dataclass
class ConfigField:
    name: str
    type: str
    default: Any = None
    label: str = ""
    cli_flag: str = ""
    options: list[str] = field(default_factory=list)
    range: list[int] | None = None
    description: str = ""


@dataclass
class ExtensionManifest:
    name: str
    version: str = "0.0.0"
    description: str = ""
    type: str = "general"
    category: str = ""
    entry: str = ""
    hooks: list[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 100
    config_schema: dict[str, ConfigField] = field(default_factory=dict)
    has_blueprint: bool = False
    blueprint_prefix: str = ""
    nav: dict = field(default_factory=dict)
    directory: Path | None = None
    source: str = "local"
    status: str = "loaded"
    status_message: str = ""
    # Plugin System Extension (C3): dependencies and capabilities
    dependencies: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    # core_shim: legacy core/xxx_core/ package name. Registers a virtual package in sys.modules
    core_shim: str = ""
    # Sandbox: trust level and permissions
    trust_level: str = TrustLevel.TRUSTED
    permissions: PermissionSet | None = None
    # Extension Module System v2: "classic" (default, IIFE <script>) or "module" (<script type="module">)
    script_type: str = "classic"
    # Unified health provider: optional callable returning a dict with
    # {available: bool, checks: dict[str, bool], reason: str, reason_i18n_key: str}.
    # Probed from the entry module by looking up a module-level get_health()
    # symbol. Used by /api/extensions and both UI pages for runtime availability.
    health_provider: Callable | None = field(default=None, repr=False, compare=False)
    # Dynamic Tauri shell tab registration. When declared, the extension
    # appears as a tab in the Tauri multi-tab shell via GET /api/tauri-shell/tabs.
    # Schema mirrors a tabs.json tab entry: {id, category, labelKey, url, mount}.
    tauri_tab: dict = field(default_factory=dict)


@dataclass
class ExtractedMetadata:
    meta_source: str = "unknown"
    format: str = "unknown"
    raw_prompt: str | None = None
    raw_negative: str | None = None
    raw_meta_json: str | None = None
    tag_source: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetailSection:
    title: str
    display_type: str = "text"
    content: Any = None
    copyable: bool = False


@dataclass
class HookEntry:
    extension_name: str
    priority: int
    callback: Callable
    enabled: bool = True
