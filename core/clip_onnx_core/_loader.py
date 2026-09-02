"""Loader for clip_onnx_core shim — delegates to extensions/builtin_clip_onnx/core_impl/."""

import importlib.util
import os
import sys

_EXT_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir,
    "extensions", "builtin_clip_onnx", "core_impl",
)


def install(name: str) -> None:
    """Register the real module into sys.modules under the shim namespace."""
    full_key = f"core.clip_onnx_core.{name}"
    if full_key in sys.modules and not getattr(sys.modules[full_key], "_is_shim", False):
        return
    real_path = os.path.join(os.path.abspath(_EXT_DIR), f"{name}.py")
    if not os.path.isfile(real_path):
        return
    spec = importlib.util.spec_from_file_location(full_key, real_path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full_key] = mod
        spec.loader.exec_module(mod)
