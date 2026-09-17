"""Shim: delegates to extensions/builtin_clip_search/core_impl/event_handler."""
from core.clip_core._loader import install as _install

_m = _install("event_handler")
globals().update({k: v for k, v in _m.__dict__.items() if not k.startswith("_")})
