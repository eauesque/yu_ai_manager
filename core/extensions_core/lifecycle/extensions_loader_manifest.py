"""Extension manifest loading helpers."""

import logging
from pathlib import Path

from core.extensions_core.extensions_defs import (
    MANIFEST_NAMES_JSON,
    MANIFEST_NAMES_YAML,
    VALID_CATEGORIES,
    VALID_TYPES,
    ConfigField,
    ExtensionManifest,
    PermissionDecl,
    PermissionSet,
    TrustLevel,
)

logger = logging.getLogger(__name__)

_CONFIG_TYPE_ALIASES = {
    "string": "str",
    "boolean": "bool",
    "number": "float",
    "integer": "int",
}


def parse_config_schema(raw: dict) -> dict[str, ConfigField]:
    """Parse manifest config_schema section."""
    result: dict[str, ConfigField] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        raw_type = str(spec.get("type", "str") or "str").strip().lower()
        result[name] = ConfigField(
            name=name,
            type=_CONFIG_TYPE_ALIASES.get(raw_type, raw_type or "str"),
            default=spec.get("default"),
            label=spec.get("label", name),
            cli_flag=spec.get("cli_flag", ""),
            options=spec.get("options", []),
            range=spec.get("range"),
            description=spec.get("description", ""),
        )
    return result


_BUNDLED_EXTENSIONS_DIR = Path(__file__).resolve().parents[3] / "extensions"


def determine_trust_level(ext_name: str, ext_dir: Path) -> TrustLevel:
    """Determine trust level from extension name.

    Only canonical bundled builtin-* directories are TRUSTED (L0).
    VERIFIED (L1) via signature verification is planned for Phase 2+.
    """
    bundled_dir = _BUNDLED_EXTENSIONS_DIR / ext_name.replace("-", "_")
    if (
        ext_name.startswith("builtin-")
        and ext_dir.name == ext_name.replace("-", "_")
        and bundled_dir.is_dir()
        and ext_dir.resolve() == bundled_dir.resolve()
    ):
        return TrustLevel.TRUSTED
    return TrustLevel.UNTRUSTED


def parse_permissions(raw: dict) -> PermissionSet | None:
    """Parse the permissions section of a manifest.

    Expected format:
        {
            "required": [{"name": "db:read", "reason": "..."}, ...],
            "optional": [{"name": "network:internet", "reason": "..."}, ...]
        }
    """
    if not raw or not isinstance(raw, dict):
        return None

    def _parse_decl_list(items) -> list:
        if not isinstance(items, list):
            return []
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(PermissionDecl(name=item))
            elif isinstance(item, dict) and "name" in item:
                result.append(PermissionDecl(
                    name=item["name"],
                    reason=item.get("reason", ""),
                ))
        return result

    return PermissionSet(
        required=_parse_decl_list(raw.get("required", [])),
        optional=_parse_decl_list(raw.get("optional", [])),
    )


def load_manifest(ext_dir: Path) -> ExtensionManifest | None:
    """Load extension manifest from extension directory."""
    from core.configuration.api import safe_load_config

    raw = None
    for name in MANIFEST_NAMES_JSON:
        json_path = ext_dir / name
        if json_path.exists():
            raw = safe_load_config(json_path, default=None)
            if raw:
                break

    if raw is None:
        for name in MANIFEST_NAMES_YAML:
            yaml_path = ext_dir / name
            if yaml_path.exists():
                raw = safe_load_config(yaml_path, default=None)
                if raw:
                    break

    if raw is None or not isinstance(raw, dict):
        return None

    if "name" not in raw:
        logger.warning(f"Missing 'name' in manifest: {ext_dir}")
        return None

    ext_type = raw.get("type", "general")
    if ext_type not in VALID_TYPES:
        logger.warning(f"Unknown type '{ext_type}' in {ext_dir}, defaulting to 'general'")
        ext_type = "general"

    config_raw = raw.get("config", {})
    config_schema_raw = raw.get("config_schema", {})

    # Parse dependencies (e.g. {"host": ">=2.50.0", "extensions": {...}, "python": [...]})
    dependencies_raw = raw.get("dependencies", {})
    if not isinstance(dependencies_raw, dict):
        dependencies_raw = {}

    # Parse capabilities (e.g. ["db:read", "network"])
    capabilities_raw = raw.get("capabilities", [])
    if not isinstance(capabilities_raw, list):
        capabilities_raw = []

    # Parse category
    ext_category = raw.get("category", "")
    if ext_category and ext_category not in VALID_CATEGORIES:
        logger.warning(f"Unknown category '{ext_category}' in {ext_dir}, ignoring")
        ext_category = ""

    # Parse permissions section
    permissions_raw = raw.get("permissions", {})
    permissions = parse_permissions(permissions_raw) if permissions_raw else None

    ext_name = raw["name"]

    # Override enabled/priority from config.json if user has toggled via UI
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
    cfg_enabled = get_extension_config_value(ext_name, "enabled")
    if cfg_enabled is not None:
        config_raw["enabled"] = cfg_enabled
    cfg_priority = get_extension_config_value(ext_name, "priority")
    if cfg_priority is not None:
        config_raw["priority"] = cfg_priority

    # Extension Module System v2: script_type
    script_type = raw.get("script_type", "classic")
    if script_type not in ("classic", "module"):
        logger.warning(
            f"Unknown script_type '{script_type}' in {ext_dir}, "
            f"defaulting to 'classic'"
        )
        script_type = "classic"

    return ExtensionManifest(
        name=ext_name,
        version=str(raw.get("version", "0.0.0")),
        description=raw.get("description", ""),
        type=ext_type,
        category=ext_category,
        entry=raw.get("entry", ""),
        hooks=raw.get("hooks", []),
        enabled=config_raw.get("enabled", True),
        priority=config_raw.get("priority", 100),
        config_schema=parse_config_schema(config_schema_raw),
        has_blueprint=raw.get("has_blueprint", False),
        blueprint_prefix=raw.get("blueprint_prefix", ""),
        nav=raw.get("nav", {}),
        directory=ext_dir,
        dependencies=dependencies_raw,
        capabilities=capabilities_raw,
        core_shim=raw.get("core_shim", ""),
        trust_level=determine_trust_level(ext_name, ext_dir),
        permissions=permissions,
        script_type=script_type,
        tauri_tab=raw.get("tauri_tab", {}),
    )
