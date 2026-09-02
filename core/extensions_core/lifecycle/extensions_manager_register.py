"""Hook/blueprint registration helpers for ExtensionManager."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from core.extensions_core.extensions_defs import HOOK_DEFINITIONS, ExtensionManifest


def register_hooks(registry, manifest: ExtensionManifest, module) -> None:
    for hook_name in manifest.hooks:
        if hook_name not in HOOK_DEFINITIONS:
            continue
        callback = getattr(module, hook_name, None)
        if callback is None or not callable(callback):
            continue
        registry.register(
            hook_name=hook_name,
            extension_name=manifest.name,
            callback=callback,
            priority=manifest.priority,
        )


def register_blueprint(blueprints: list[tuple[Any, str]], manifest: ExtensionManifest, module) -> None:
    if not manifest.has_blueprint:
        return
    get_bp = getattr(module, "get_blueprint", None)
    if get_bp is None or not callable(get_bp):
        logger.warning(f"{manifest.name}: has_blueprint=true but no get_blueprint() function")
        return
    try:
        bp = get_bp()
        if bp is None:
            return
        prefix = manifest.blueprint_prefix
        if not prefix:
            safe_name = manifest.name.replace("builtin-", "").replace("-", "_")
            prefix = f"/ext/{safe_name}"
        blueprints.append((bp, prefix))
        logger.info(f"{manifest.name}: Blueprint registered at {prefix}")
    except ImportError as e:
        # Missing optional hardware dependency (e.g. cv2, hailo_platform) — expected on non-Hailo systems
        logger.warning(f"{manifest.name}: Blueprint registration skipped (missing dependency: {e})")
    except Exception as e:
        logger.error(f"{manifest.name}: Blueprint registration failed: {e}", exc_info=True)
