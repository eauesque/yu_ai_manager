"""Windows NVIDIA DLL preloading.

When multiple CUDA / cuDNN installations coexist on a Windows machine
(pip-installed ``nvidia-cudnn-cu12`` in the venv, plus a system CUDA Toolkit
or system cuDNN install), simply prepending the venv ``nvidia/cudnn/bin``
directory to ``os.environ["PATH"]`` is **not enough**:

- Python 3.8+ on Windows uses safe DLL search for extension modules and
  ignores PATH for them.
- Lazy-loaded cuDNN sub-libraries (``cudnn_engines_runtime_compiled64_9.dll``
  etc.) are loaded by ``cudnn64_9.dll`` via plain ``LoadLibrary`` which still
  hits the system search order. The first matching DLL on PATH wins, even if
  another cuDNN was already loaded by the same process from a different path.
- The result is a process with cuDNN main + sub-libraries from **different
  builds** (e.g. venv 9.19 main + system 9.20 sub-libs), which manifests as:
  - ``CUDNN_FE failure 7: GRAPH_EXECUTION_FAILED`` / ``Plan index -1 is invalid``
  - ``CUDNN failure 1002: CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH``

To make this deterministic we **explicitly preload** every venv-bundled CUDA
and cuDNN DLL via ``ctypes.WinDLL`` with its absolute path BEFORE onnxruntime
ever touches CUDA. Once a DLL is in the per-process loader cache, subsequent
``LoadLibrary("<basename>")`` calls return the cached venv handle regardless
of PATH or system installations.

Must be called before importing / initialising onnxruntime CUDA EP.
"""

import logging
import os
from pathlib import Path

from .detect import is_windows

logger = logging.getLogger(__name__)

_registered = False

# Dependency-ordered preload list. The order is critical:
# 1. CUDA runtime first (everything else depends on it)
# 2. JIT compilers (nvrtc / nvJitLink) — needed by runtime-compiled cuDNN engines
# 3. Linear algebra (cuBLAS, cuFFT, cuRAND) — depend on the runtime
# 4. cuDNN sub-libraries (heuristic, ops, graph, engines) — must be loaded before
#    the main ``cudnn64_9.dll`` so that when the main DLL later resolves them
#    by base name they hit the loader cache instead of falling back to PATH.
# 5. cuDNN main library
#
# All filenames target onnxruntime-gpu built against CUDA 12.x (cuDNN 9.x).
# Missing files are silently skipped — different ORT builds may not need every
# entry, and we never want preload to abort initialisation.
_PRELOAD_ORDER: list[tuple[str, str]] = [
    # 1. CUDA runtime
    ("cuda_runtime", "cudart64_12.dll"),
    # 2. JIT / runtime compilation support
    ("cuda_nvrtc", "nvrtc64_120_0.dll"),
    ("cuda_nvrtc", "nvrtc-builtins64_129.dll"),
    ("nvjitlink", "nvJitLink_120_0.dll"),
    # 3. Linear algebra
    ("cublas", "cublasLt64_12.dll"),
    ("cublas", "cublas64_12.dll"),
    ("cufft", "cufft64_11.dll"),
    ("cufft", "cufftw64_11.dll"),
    ("curand", "curand64_10.dll"),
    # 4. cuDNN sub-libraries (load before main)
    ("cudnn", "cudnn_engines_runtime_compiled64_9.dll"),
    ("cudnn", "cudnn_engines_precompiled64_9.dll"),
    ("cudnn", "cudnn_heuristic64_9.dll"),
    ("cudnn", "cudnn_ops64_9.dll"),
    ("cudnn", "cudnn_adv64_9.dll"),
    ("cudnn", "cudnn_graph64_9.dll"),
    ("cudnn", "cudnn_cnn64_9.dll"),
    # 5. cuDNN main library
    ("cudnn", "cudnn64_9.dll"),
]


def register_nvidia_dll_dirs() -> None:
    """Pin pip nvidia package DLLs into the process loader cache (Windows only)."""
    global _registered
    if _registered:
        return
    _registered = True

    if not is_windows():
        return

    try:
        import nvidia
    except ImportError:
        return

    nvidia_root = Path(nvidia.__path__[0])

    # Step 1: Preload each DLL by absolute path so the loader cache contains
    # the venv version. Order matters — see _PRELOAD_ORDER docstring.
    import ctypes  # local import: only needed on Windows

    loaded_count = 0
    skipped_missing = 0
    failed: list[str] = []
    for pkg, filename in _PRELOAD_ORDER:
        dll = nvidia_root / pkg / "bin" / filename
        if not dll.is_file():
            skipped_missing += 1
            continue
        try:
            ctypes.WinDLL(str(dll))
            loaded_count += 1
        except OSError as exc:
            # Don't abort on partial failures — some DLLs may genuinely be
            # missing on certain CUDA minor versions, and we want the rest
            # of the load chain to succeed.
            failed.append(f"{filename} ({exc})")

    if loaded_count > 0:
        logger.info(
            "Preloaded %d NVIDIA DLLs from %s (skipped missing: %d, failed: %d)",
            loaded_count, nvidia_root, skipped_missing, len(failed),
        )
    if failed:
        logger.warning("NVIDIA DLL preload failures: %s", ", ".join(failed))

    # Step 2: Also extend PATH so any DLLs we did NOT explicitly preload
    # (future packages, optional helper libs) can still be located by name.
    # The preload above is what actually fixes the system-DLL hijacking;
    # PATH manipulation is just defence in depth.
    dirs_to_add = [str(d) for d in nvidia_root.glob("*/bin") if d.is_dir()]
    if dirs_to_add:
        current_path = os.environ.get("PATH", "")
        new_entries = [d for d in dirs_to_add if d not in current_path]
        if new_entries:
            os.environ["PATH"] = (
                os.pathsep.join(new_entries) + os.pathsep + current_path
            )
            for d in new_entries:
                logger.debug("Added to PATH: %s", d)
