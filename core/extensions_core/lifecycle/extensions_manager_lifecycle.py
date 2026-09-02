"""Lifecycle helpers for ExtensionManager.

Sandbox gate and isolation helpers are in lifecycle_sandbox.py.
This module provides discover_and_load_extensions, load_single_extension,
unload_extension, and set_extension_enabled.
"""

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.extensions_core.extensions_defs import ExtensionManifest, TrustLevel

from ..sandbox.process_isolation import get_isolated_process
from .extensions_db_migrate import run_extension_db_migrations
from .extensions_deps import resolve_load_order
from .extensions_loader import load_extension_module, load_manifest
from .extensions_manager_audit import apply_audit_results, audit_extension
from .extensions_manager_register import register_blueprint, register_hooks

# Re-export sandbox helpers under original private names for compatibility
from .lifecycle_sandbox import (  # noqa: F401
    load_isolated as _load_isolated,
)
from .lifecycle_sandbox import (
    record_integrity_baseline as _record_integrity_baseline,
)
from .lifecycle_sandbox import (
    register_core_shim_for as _register_core_shim,
)
from .lifecycle_sandbox import (
    sandbox_gate as _sandbox_gate,
)
from .lifecycle_sandbox import (
    should_isolate as _should_isolate,
)
from .lifecycle_sandbox import (
    start_runtime_guards as _start_runtime_guards,
)


def _load_enabled_extension(manifest, registry, modules, blueprints) -> bool:
    """Run the shared gate/isolation/import path for every lifecycle entrypoint."""
    if manifest.trust_level != TrustLevel.TRUSTED:
        if not _sandbox_gate(manifest):
            return False
        if _should_isolate(manifest):
            if not _load_isolated(manifest, registry, blueprints):
                return False
            _register_core_shim(manifest)
            return True

    module = load_extension_module(manifest)
    if module is None:
        return False
    if not apply_audit_results(manifest, audit_extension(manifest, module)):
        return False

    register_hooks(registry, manifest, module)
    register_blueprint(blueprints, manifest, module)
    from .extensions_health import register_health_provider
    register_health_provider(manifest, module)
    _register_core_shim(manifest)
    if manifest.trust_level != TrustLevel.TRUSTED and manifest.directory:
        _record_integrity_baseline(manifest)
    modules[manifest.name] = module
    return True


def discover_and_load_extensions(
    extensions_dir: Path,
    registry,
    manifests: dict[str, ExtensionManifest],
    modules: dict[str, Any],
    blueprints: list[tuple[Any, str]],
) -> int:
    if not extensions_dir.exists():
        return 0

    # Phase 1: Load all manifests first
    discovered: dict[str, tuple[Path, ExtensionManifest]] = {}
    for entry in sorted(extensions_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        manifest = load_manifest(entry)
        if manifest is None:
            continue
        discovered[manifest.name] = (entry, manifest)

    # Phase 2: Determine load order based on dependencies
    load_order = list(discovered.keys())
    has_deps = any(
        getattr(m, "dependencies", None) for _, m in discovered.values()
    )
    if has_deps:
        try:
            disc_manifests = {n: m for n, (_, m) in discovered.items()}
            load_order = resolve_load_order(disc_manifests)
        except Exception as exc:
            # Fall back to default order if dependency resolution fails
            logger.warning(f"Dependency resolution failed, using default order: {exc}")

    # Phase 3: Load in determined order
    loaded = 0
    for name in load_order:
        if name not in discovered:
            continue
        _, manifest = discovered[name]

        if not manifest.enabled:
            manifest.status = "disabled"
            logger.info(f"{manifest.name} v{manifest.version} (disabled)")
            manifests[manifest.name] = manifest
            continue

        manifests[manifest.name] = manifest
        if not _load_enabled_extension(manifest, registry, modules, blueprints):
            continue

        hooks_str = ", ".join(manifest.hooks) if manifest.hooks else "none"
        logger.info(
            f"{manifest.name} v{manifest.version} "
            f"(type={manifest.type}, priority={manifest.priority}, hooks=[{hooks_str}])"
        )
        loaded += 1

    # Phase 4: Run extension DB migrations
    if loaded > 0:
        try:
            from core.services_core.db_api import get_db
            con = get_db()
            run_extension_db_migrations(registry, modules, con)
        except Exception as exc:
            logger.warning(f"Extension DB migration skipped: {exc}")

    # Phase 5: Install ImportGuard + start IntegrityMonitor
    _start_runtime_guards()

    return loaded


def load_single_extension(
    ext_dir: Path,
    registry,
    manifests: dict[str, ExtensionManifest],
    modules: dict[str, Any],
    unload_fn,
    blueprints: list[tuple[Any, str]] | None = None,
) -> ExtensionManifest | None:
    blueprints = [] if blueprints is None else blueprints
    manifest = load_manifest(ext_dir)
    if manifest is None:
        return None
    if manifest.name in manifests:
        unload_fn(manifest.name)
    if manifest.enabled:
        _load_enabled_extension(manifest, registry, modules, blueprints)
    manifests[manifest.name] = manifest
    manifest.directory = ext_dir
    return manifest


def unload_extension(name: str, registry, manifests: dict[str, ExtensionManifest], modules: dict[str, Any]) -> bool:
    if name not in manifests:
        return False

    # Phase 4: Stop isolated process
    try:
        proc = get_isolated_process(name)
        if proc:
            proc.stop()
    except Exception:
        # The extension is being torn down; a process that would not stop is
        # still running with whatever it had.
        logger.warning("isolated process for %s did not stop", name, exc_info=True)

    registry.unregister_all(name)
    module_name = f"ext_{name.replace('-', '_')}"
    sys.modules.pop(module_name, None)
    modules.pop(name, None)
    manifests.pop(name, None)
    from .extensions_health import invalidate_health_cache
    invalidate_health_cache(name)
    return True


def set_extension_enabled(
    name: str,
    enabled: bool,
    registry,
    manifests: dict[str, ExtensionManifest],
    modules: dict[str, Any],
    blueprints: list[tuple[Any, str]] | None = None,
) -> bool:
    blueprints = [] if blueprints is None else blueprints
    manifest = manifests.get(name)
    if manifest is None:
        return False
    manifest.enabled = enabled
    registry.set_enabled(name, enabled)
    if not enabled:
        proc = get_isolated_process(name)
        if proc:
            proc.stop()
        manifest.status = "disabled"
        manifest.status_message = ""
    elif name not in modules:
        proc = get_isolated_process(name)
        if proc and proc.is_alive():
            return True
        return _load_enabled_extension(manifest, registry, modules, blueprints)
    return True
