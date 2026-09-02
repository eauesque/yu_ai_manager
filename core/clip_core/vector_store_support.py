"""Shim: delegates to extensions/builtin_clip_search/core_impl/vector_store_support."""
from core.clip_core._loader import install as _install

_m = _install("vector_store_support")
globals().update({k: v for k, v in _m.__dict__.items() if not k.startswith("_")})
