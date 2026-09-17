"""Shim: delegates to extensions/builtin_clip_search/core_impl/encoder_abc."""
from core.clip_core._loader import install as _install

_m = _install("encoder_abc")
# Re-export public API so ``from core.clip_core.encoder_abc import X`` works
globals().update({k: v for k, v in _m.__dict__.items() if not k.startswith("_")})
