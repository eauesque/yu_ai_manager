"""Shim: delegates to extensions/builtin_clip_search/core_impl/search_cache.py."""
from core.clip_core._loader import install as _install

_m = _install("search_cache")
globals().update({k: v for k, v in _m.__dict__.items() if not k.startswith("_")})
