"""Extension manifest serialization helpers."""

from core.extensions_core.extensions_defs import ExtensionManifest

from .extensions_health import compute_health


def manifest_to_dict(m: ExtensionManifest) -> dict:
    config_schema = {}
    for name, cf in m.config_schema.items():
        config_schema[name] = {
            "type": cf.type,
            "default": cf.default,
            "label": cf.label,
            "cli_flag": cf.cli_flag,
        }
        if cf.options:
            config_schema[name]["options"] = cf.options
        if cf.range:
            config_schema[name]["range"] = cf.range
        if cf.description:
            config_schema[name]["description"] = cf.description

    return {
        "name": m.name,
        "version": m.version,
        "description": m.description,
        "type": m.type,
        "category": m.category or "",
        "entry": m.entry,
        "hooks": m.hooks,
        "enabled": m.enabled,
        "priority": m.priority,
        "config_schema": config_schema,
        "source": m.source,
        "has_blueprint": m.has_blueprint,
        "blueprint_prefix": m.blueprint_prefix or None,
        "nav": m.nav,
        "status": m.status,
        "status_message": m.status_message,
        "trust_level": str(m.trust_level) if m.trust_level else "trusted",
        # Skip health for disabled extensions — probing them is wasteful and
        # would surface an "Available" badge next to "Disabled", which is
        # confusing. Re-enabling triggers a fresh probe via set_extension_enabled.
        "health": compute_health(m) if m.enabled else None,
    }
