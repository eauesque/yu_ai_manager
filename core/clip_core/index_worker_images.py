"""Shim: delegates to extensions/builtin_clip_search/core_impl/index_worker_images.py."""
from core.clip_core._loader import install as _install

_m = _install("index_worker_images")
globals().update({k: v for k, v in _m.__dict__.items() if not k.startswith("_")})
