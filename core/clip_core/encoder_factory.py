"""Shim: delegates to extensions/builtin_clip_search/core_impl/encoder_factory."""
from core.clip_core._loader import install as _install

_m = _install("encoder_factory")
globals().update({k: v for k, v in _m.__dict__.items() if not k.startswith("_")})
