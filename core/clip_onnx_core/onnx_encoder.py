"""Shim: delegates to extensions/builtin_clip_onnx/core_impl/onnx_encoder.py."""
_is_shim = True
from . import _loader as _l

_l.install("onnx_encoder")
import sys as _sys

globals().update(vars(_sys.modules[__name__]))
