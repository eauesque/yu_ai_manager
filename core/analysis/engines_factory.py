"""Compatibility re-export for core.analysis.engines_factory.

This package exists because the real implementation lives in the builtin
analysis extension package.
"""
from importlib import import_module

_impl = import_module("extensions.builtin_analysis.core_impl.engines_factory")
for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)
__all__ = [n for n in dir(_impl) if not n.startswith("_")]
