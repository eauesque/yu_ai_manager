"""Print the appropriate onnxruntime extra name for this machine.

Stdlib-only — no project imports — so it can run before uv has set up a venv
with project deps. Prints exactly one token to stdout:

    gpu       NVIDIA CUDA (nvidia-smi present)
    rocm      AMD ROCm on Linux (rocminfo or /opt/rocm)
    directml  Windows fallback (DirectML works on any DX12 GPU, ~all Windows
              machines from the last ~10 years; safer default than CPU)
    silicon   Apple Silicon (macOS arm64 — native ARM64 wheel + CoreML EP)
    cpu       everything else (Linux without ROCm, Intel macOS, ...)

Caveats:
  - This is a heuristic suitable for first-launch defaults. Presence of
    `nvidia-smi` does NOT guarantee that onnxruntime's CUDA EP will actually
    initialize — driver/CUDA toolkit/cuDNN version mismatches still cause
    silent CPU fallback at session creation time. The runtime registry
    (extensions/builtin_inference/core_impl/ort_provider.py:get_active_sessions)
    surfaces such fallbacks in the WebUI Inference Info panel; rely on that
    for "is CUDA actually working" rather than this detection.
  - Override the choice by editing `.onnx_extra` (one token: cpu/gpu/directml
    /rocm) or running `bin/uv run python scripts/install_onnx.py --variant
    <name>`. start.bat / start.sh consume the marker on every launch.
  - WSL2 inside Windows: `nvidia-smi` from the Windows host may be visible
    even when the WSL2 distro lacks CUDA libraries. If that's your setup,
    set the marker to `cpu` manually and ignore the auto-detection.

Used by start.bat / start.sh and scripts/install_onnx.py.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _has_nvidia() -> bool:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _has_rocm_linux() -> bool:
    if sys.platform != "linux":
        return False
    if Path("/opt/rocm").exists():
        return True
    try:
        r = subprocess.run(
            ["rocminfo"], capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def detect() -> str:
    if _has_nvidia():
        return "gpu"
    if _has_rocm_linux():
        return "rocm"
    if sys.platform == "win32":
        # DirectML is available on virtually any DX12-capable Windows GPU
        # (Intel iGPU, AMD, NVIDIA fallback). The actual `onnxruntime-directml`
        # wheel itself just needs Windows; it falls back to CPU EP at runtime
        # if no compatible adapter is present, so this is a safe default.
        return "directml"
    if _is_apple_silicon():
        # Native arm64 wheel with CoreML ExecutionProvider built in.
        return "silicon"
    return "cpu"


def main() -> None:
    sys.stdout.write(detect())
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
