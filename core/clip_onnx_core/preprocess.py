"""Shim: delegates to extensions/builtin_clip_onnx/core_impl/preprocess.py."""
_is_shim = True
from . import _loader as _l

_l.install("preprocess")
import sys as _sys

globals().update(vars(_sys.modules[__name__]))
