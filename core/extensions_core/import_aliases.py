"""Compatibility alias installation for relocated extension modules."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

# Module relocation map: module name -> subpackage name
MOVED_MODULES = {
    # sandbox/
    "sandbox_proxy": "sandbox",
    "sandbox_http": "sandbox",
    "process_isolation": "sandbox",
    "isolation_worker": "sandbox",
    "isolation_hooks": "sandbox",
    "os_isolation": "sandbox",
    "os_isolation_profiles": "sandbox",
    "import_guard": "sandbox",
    "integrity_monitor": "sandbox",
    # validation/
    "code_verifier": "validation",
    "manifest_authority": "validation",
    "extension_permissions": "validation",
    # token_mgmt/
    "capability_token": "token_mgmt",
    "token_revocation": "token_mgmt",
    # lifecycle/
    "extensions_loader": "lifecycle",
    "extensions_loader_manifest": "lifecycle",
    "extensions_loader_module": "lifecycle",
    "extensions_manager": "lifecycle",
    "extensions_manager_audit": "lifecycle",
    "extensions_manager_lifecycle": "lifecycle",
    "extensions_manager_ops": "lifecycle",
    "extensions_manager_register": "lifecycle",
    "extensions_manager_view": "lifecycle",
    "extensions_manifest_view": "lifecycle",
    "extensions_hooks": "lifecycle",
    "extensions_hooks_invoke": "lifecycle",
    "extensions_hooks_view": "lifecycle",
    "extensions_admin": "lifecycle",
    "extensions_db_migrate": "lifecycle",
    "extensions_core_shim": "lifecycle",
    "extensions_deps": "lifecycle",
    "extensions_deps_version": "lifecycle",
    "runtime": "lifecycle",
    "extensions_api_config_ops": "lifecycle",
    "extensions_api_git_helpers": "lifecycle",
    "extensions_api_git_ops": "lifecycle",
    "extensions_api_ops": "lifecycle",
    "extensions_marketplace": "lifecycle",
    "extensions_marketplace_fetch": "lifecycle",
}

PKG = "core.extensions_core"
ALIASES = {
    f"{PKG}.{name}": f"{PKG}.{subpkg}.{name}"
    for name, subpkg in MOVED_MODULES.items()
}


class AliasFinder(importlib.abc.MetaPathFinder):
    """Resolve legacy extension module paths to their relocated modules."""

    def find_spec(self, fullname, path, target=None):
        actual = ALIASES.get(fullname)
        if actual is None:
            return None
        return importlib.machinery.ModuleSpec(fullname, AliasLoader(actual))


class AliasLoader(importlib.abc.Loader):
    """Import the real module and register it under the old path name."""

    def __init__(self, actual_name):
        self._actual = actual_name
        self._orig_spec = None
        self._orig_package = None

    def create_module(self, spec):
        mod = importlib.import_module(self._actual)
        self._orig_spec = getattr(mod, "__spec__", None)
        self._orig_package = getattr(mod, "__package__", None)
        return mod

    def exec_module(self, module):
        if self._orig_spec is not None:
            module.__spec__ = self._orig_spec
        if self._orig_package is not None:
            module.__package__ = self._orig_package


def install_import_aliases() -> None:
    """Install the alias finder once."""
    if not any(isinstance(finder, AliasFinder) for finder in sys.meta_path):
        sys.meta_path.append(AliasFinder())
