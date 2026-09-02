"""Compatibility re-export for core.analysis.engines_openai."""
from importlib import import_module

_impl = import_module("extensions.builtin_analysis.core_impl.engines_openai")
for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)
__all__ = [n for n in dir(_impl) if not n.startswith("_")]
