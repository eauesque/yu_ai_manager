"""Compatibility re-export for core.analysis.ollama_utils.

This module intentionally remains as a compatibility bridge for the
``builtin-analysis`` extension. Prefer direct imports only where a stable
non-bridge module path exists.
"""
from importlib import import_module

_impl = import_module("extensions.builtin_analysis.core_impl.ollama_utils")
for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)
__all__ = [n for n in dir(_impl) if not n.startswith("_")]
