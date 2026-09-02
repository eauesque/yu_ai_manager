"""Read-only view helpers for extension manager."""


from core.extensions_core.extensions_defs import HOOK_DEFINITIONS

from .extensions_manifest_view import manifest_to_dict


def get_extension_info(manifests: dict[str, object], name: str):
    manifest = manifests.get(name)
    if manifest is None:
        return None
    return manifest_to_dict(manifest)


def list_extensions(manifests: dict[str, object]) -> list[dict]:
    return [manifest_to_dict(manifests[name]) for name in sorted(manifests.keys())]


def get_hook_info(registry) -> dict:
    info = registry.get_registered()
    result = {}
    for hook_name, entries in info.items():
        result[hook_name] = {
            "mode": HOOK_DEFINITIONS.get(hook_name, "unknown"),
            "handlers": entries,
        }
    return result
