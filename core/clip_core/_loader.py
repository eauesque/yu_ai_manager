"""Internal helper to load modules from the builtin-clip-search extension.

Each shim module calls ``install("module_name")`` which loads the real
module from the extension directory and patches ``sys.modules`` so that
all subsequent imports of ``core.clip_core.<name>`` resolve to the real
extension module transparently.
"""

import importlib.util
import os
import sys

# Absolute path to the extension core_impl directory
_EXT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    os.pardir, os.pardir,
    "extensions", "builtin_clip_search", "core_impl",
))

# Track which modules have been loaded from the extension
_loaded: set = set()


def install(name: str):
    """Load extension module and register it as ``core.clip_core.<name>``.

    Returns the loaded module so the shim can populate its own namespace.
    """
    fqn = f"core.clip_core.{name}"

    # Avoid double-loading; the fqn may already be in sys.modules
    # as the shim itself, so we track separately.
    if name in _loaded:
        return sys.modules[fqn]

    src = os.path.join(_EXT_DIR, f"{name}.py")
    if not os.path.isfile(src):
        raise ImportError(
            f"Extension source not found: {src}  "
            f"(is builtin-clip-search installed?)"
        )
    spec = importlib.util.spec_from_file_location(fqn, src)
    mod = importlib.util.module_from_spec(spec)
    # Replace the shim module in sys.modules with the real one
    sys.modules[fqn] = mod
    _loaded.add(name)
    spec.loader.exec_module(mod)
    return mod
