"""Extension manager implementation."""

from pathlib import Path
from typing import Any

from core.extensions_core.extensions_defs import ExtensionManifest

from .extensions_hooks import HookRegistry
from .extensions_manager_ops import (
    discover_and_load_extensions,
    load_single_extension,
    register_blueprint,
    register_hooks,
    set_extension_enabled,
    unload_extension,
)
from .extensions_manager_view import (
    get_extension_info as _get_extension_info,
)
from .extensions_manager_view import (
    get_hook_info as _get_hook_info,
)
from .extensions_manager_view import (
    list_extensions as _list_extensions,
)


class ExtensionManager:
    """Extension discovery, loading, and hook/blueprint registry."""

    def __init__(self, extensions_dir: Path | None = None) -> None:
        self.extensions_dir = extensions_dir or Path("extensions")
        self.registry = HookRegistry()
        self.manifests: dict[str, ExtensionManifest] = {}
        self._modules: dict[str, Any] = {}
        self._blueprints: list[tuple[Any, str]] = []

    def discover_and_load(self) -> int:
        return discover_and_load_extensions(
            self.extensions_dir,
            self.registry,
            self.manifests,
            self._modules,
            self._blueprints,
        )

    def _register_hooks(self, manifest: ExtensionManifest, module) -> None:
        register_hooks(self.registry, manifest, module)

    def _register_blueprint(self, manifest: ExtensionManifest, module) -> None:
        register_blueprint(self._blueprints, manifest, module)

    def get_blueprints(self) -> list[tuple[Any, str]]:
        return list(self._blueprints)

    def load_single(self, ext_dir: Path) -> ExtensionManifest | None:
        return load_single_extension(
            ext_dir,
            self.registry,
            self.manifests,
            self._modules,
            self.unload,
            self._blueprints,
        )

    def unload(self, name: str) -> bool:
        return unload_extension(name, self.registry, self.manifests, self._modules)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        return set_extension_enabled(
            name, enabled, self.registry, self.manifests, self._modules, self._blueprints,
        )

    def get_extension_info(self, name: str) -> dict | None:
        return _get_extension_info(self.manifests, name)

    def list_extensions(self) -> list[dict]:
        return _list_extensions(self.manifests)

    def get_hook_info(self) -> dict:
        return _get_hook_info(self.registry)

    def invoke_hook(self, hook_name: str, *args, **kwargs) -> Any:
        return self.registry.invoke(hook_name, *args, **kwargs)
