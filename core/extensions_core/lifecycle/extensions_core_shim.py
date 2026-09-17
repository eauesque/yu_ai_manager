"""Core shim registration for backward-compatible imports.

Registers extension core_impl/ directories as virtual ``core.xxx_core``
packages in sys.modules. Declared via the ``core_shim`` field in extension.json.

Callers:
- runtime_app.py (at server startup, before Blueprint registration)
- extensions_manager_lifecycle.py (at extension load time, idempotent)
- conftest.py (at test execution time)
"""

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

logger = logging.getLogger(__name__)

_EXTENSIONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "extensions"


def register_core_shim(shim_name: str, core_impl_dir: Path) -> None:
    """Register a single core shim virtual package.

    Args:
        shim_name: Package suffix (e.g. "chatlog_core")
        core_impl_dir: Path to extension's core_impl/ directory
    """
    full_name = f"core.{shim_name}"
    if full_name in sys.modules:
        return

    if not core_impl_dir.is_dir():
        logger.warning(f"core_shim '{shim_name}': core_impl/ not found at {core_impl_dir}")
        return

    # If core_impl/__init__.py has public symbols, load properly via module_from_spec
    # (module_from_spec sets __spec__, enabling correct relative imports on Windows)
    init_file = core_impl_dir / "__init__.py"
    spec = None
    if init_file.exists() and init_file.stat().st_size > 100:
        spec = importlib.util.spec_from_file_location(
            full_name, str(init_file),
            submodule_search_locations=[str(core_impl_dir)],
        )

    if spec:
        pkg = importlib.util.module_from_spec(spec)
    else:
        pkg = types.ModuleType(full_name)
        pkg.__path__ = [str(core_impl_dir)]
        pkg.__package__ = full_name
        pkg.__file__ = str(core_impl_dir / "__init__.py")
        pkg.__loader__ = None

    # Register in sys.modules first so __init__.py relative imports resolve correctly
    sys.modules[full_name] = pkg

    if spec and spec.loader:
        try:
            spec.loader.exec_module(pkg)
        except Exception as exc:
            logger.warning(f"Failed to load core_impl/__init__.py for {shim_name}: {exc}")
    logger.debug(f"Registered core shim: {full_name} -> {core_impl_dir}")


def register_all_core_shims(extensions_dir: Path | None = None) -> int:
    """Scan all extension manifests and register core_shim virtual packages."""
    ext_dir = extensions_dir or _EXTENSIONS_DIR
    if not ext_dir.exists():
        return 0

    count = 0
    for entry in sorted(ext_dir.iterdir()):
        manifest_path = entry / "extension.json"
        if not manifest_path.exists():
            continue
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        shim_name = raw.get("core_shim", "")
        if not shim_name:
            continue
        core_impl_dir = entry / "core_impl"
        register_core_shim(shim_name, core_impl_dir)
        count += 1

    return count
