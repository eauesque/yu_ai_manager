# Compatibility shim -- the real implementation lives at
# extensions/builtin_chatlog/core_impl/.
# This package re-exports every submodule so that existing
# ``from core.chatlog_core.<mod> import ...`` statements keep working.

import importlib as _il
import sys as _sys

_REAL_PKG = "extensions.builtin_chatlog.core_impl"

_SUBMODULES = [
    "chatlog_ai",
    "entity_extractor",
    "importer",
    "parser_chatgpt",
    "parser_claude",
    "parser_openwebui",
    "store",
    "store_ai",
    "store_crud",
    "store_entities",
    "store_search",
    "text_search",
]


def _install_shims():
    """Register real submodules under the ``core.chatlog_core.*`` namespace."""
    for name in _SUBMODULES:
        alias = f"core.chatlog_core.{name}"
        if alias in _sys.modules:
            continue
        try:
            real = _il.import_module(f"{_REAL_PKG}.{name}")
            _sys.modules[alias] = real
        except ModuleNotFoundError:
            # Submodule may not exist yet; skip silently.
            pass


_install_shims()
