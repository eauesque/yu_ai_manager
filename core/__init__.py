"""Core package."""

import logging
from importlib import import_module

logger = logging.getLogger(__name__)

# Pin venv-bundled CUDA / cuDNN DLLs into the process loader cache as early as
# possible — BEFORE any extension can import ctranslate2, torch, or onnxruntime.
# Each of those bundles its own CUDA libraries, and once one of them puts a
# ``cudnn64_9.dll`` (or any sub-library) in the loader cache, all subsequent
# code in the process is stuck with that version. When system-installed cuDNN
# from a different CUDA major version (e.g. CUDA 13 / cuDNN 9.20) leaks into
# the search path, the result is mixed sub-library versions and runtime
# failures like ``CUDNN_FE failure 7 / Plan index -1 is invalid`` or
# ``CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH`` in WD-Tagger / YOLO Conv ops.
#
# This call lives in ``core/__init__.py`` so that the FIRST ``import core.x``
# anywhere in the codebase triggers the preload before extensions get a chance
# to load their own CUDA stack. The function is idempotent (guarded by an
# internal ``_registered`` flag) and a no-op on non-Windows platforms or when
# the ``nvidia`` package is not installed.
try:
    from .platform.nvidia_dll import register_nvidia_dll_dirs as _register_nvidia_dll_dirs

    _register_nvidia_dll_dirs()
except Exception:  # pragma: no cover - never block import on preload failure
    logger.warning("step failed", exc_info=True)


def __getattr__(name: str):
    if name == "analysis":
        return import_module("core.analysis")
    raise AttributeError(name)
