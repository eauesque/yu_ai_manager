"""GPU detection module.

Detects GPUs on the system and determines available inference backends.
Supports detection of NVIDIA (CUDA), AMD (ROCm), DirectML, and CoreML.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from core.platform.detect import is_macos, is_windows

logger = logging.getLogger(__name__)

# subprocess timeout (seconds)
_SUBPROCESS_TIMEOUT = 5


@dataclass
class GpuInfo:
    """Detected GPU information."""

    vendor: str = "unknown"
    name: str = "unknown"
    cuda_available: bool = False
    rocm_available: bool = False
    directml_available: bool = False
    coreml_available: bool = False
    openvino_available: bool = False
    vitisai_available: bool = False
    recommended_ort_package: str = "onnxruntime"

    def summary(self) -> str:
        """Return a human-readable summary string."""
        caps: list[str] = []
        if self.cuda_available:
            caps.append("CUDA")
        if self.rocm_available:
            caps.append("ROCm")
        if self.vitisai_available:
            caps.append("Vitis AI (Ryzen AI NPU)")
        if self.directml_available:
            caps.append("DirectML")
        if self.openvino_available:
            caps.append("OpenVINO")
        if self.coreml_available:
            caps.append("CoreML")
        if not caps:
            caps.append("CPU only")
        return f"{self.vendor} {self.name} ({', '.join(caps)})"


def _detect_nvidia() -> tuple[bool, str]:
    """Detect NVIDIA GPU via nvidia-smi.

    Returns:
        (cuda_available, gpu_name)
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().splitlines()[0].strip()
            logger.info("NVIDIA GPU 検出: %s", gpu_name)
            return True, gpu_name
    except FileNotFoundError:
        logger.debug("nvidia-smi が見つからない (NVIDIA GPU なし)")
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi がタイムアウト")
    except Exception:
        logger.debug("NVIDIA GPU 検出中にエラー", exc_info=True)
    return False, ""


def _detect_rocm() -> tuple[bool, str]:
    """Detect AMD ROCm-compatible GPU via rocminfo.

    Returns:
        (rocm_available, gpu_name)
    """
    try:
        result = subprocess.run(
            ["rocminfo"],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode == 0 and "Agent" in result.stdout:
            # Extract GPU name from rocminfo output
            for line in result.stdout.splitlines():
                if "Marketing Name" in line:
                    gpu_name = line.split(":")[-1].strip()
                    if gpu_name:
                        logger.info("AMD ROCm GPU 検出: %s", gpu_name)
                        return True, gpu_name
            logger.info("AMD ROCm 環境を検出 (GPU 名は不明)")
            return True, "AMD GPU"
    except FileNotFoundError:
        logger.debug("rocminfo が見つからない (ROCm 環境なし)")
    except subprocess.TimeoutExpired:
        logger.warning("rocminfo がタイムアウト")
    except Exception:
        logger.debug("ROCm 検出中にエラー", exc_info=True)
    return False, ""


def _detect_rocm_windows() -> tuple[bool, str]:
    """Detect AMD ROCm/HIP SDK on Windows via HIP_PATH/ROCM_PATH and hipInfo.exe.

    Returns:
        (rocm_available, gpu_name)
    """
    import os
    from pathlib import Path

    hip_path = os.environ.get("HIP_PATH") or os.environ.get("ROCM_PATH")
    if not hip_path:
        default = Path(r"C:\Program Files\AMD\ROCm")
        if default.is_dir():
            hip_path = str(default)

    if not hip_path:
        return False, ""

    hip_dir = Path(hip_path)

    # Locate hipInfo.exe (flat or versioned subdirectory layout)
    hipinfo: Path | None = None
    candidate = hip_dir / "bin" / "hipInfo.exe"
    if candidate.is_file():
        hipinfo = candidate
    else:
        try:
            for sub in sorted(hip_dir.iterdir(), reverse=True):
                c = sub / "bin" / "hipInfo.exe"
                if c.is_file():
                    hipinfo = c
                    break
        except OSError:
            pass

    if hipinfo is None:
        logger.debug("HIP_PATH/ROCM_PATH が設定されているが hipInfo.exe が見つからない: %s", hip_path)
        return False, ""

    try:
        result = subprocess.run(
            [str(hipinfo)],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Name:" in line or "Device Name:" in line:
                    gpu_name = line.split(":", 1)[-1].strip()
                    if gpu_name:
                        logger.info("AMD ROCm/HIP GPU 検出 (Windows): %s", gpu_name)
                        return True, gpu_name
            logger.info("AMD ROCm/HIP 環境を検出 (Windows, GPU 名は不明)")
            return True, "AMD GPU"
    except subprocess.TimeoutExpired:
        logger.warning("hipInfo.exe がタイムアウト")
    except OSError:
        pass

    logger.info("AMD HIP SDK を検出 (Windows): %s", hip_path)
    return True, "AMD GPU (HIP SDK)"


def _detect_directml() -> bool:
    """Check DirectML availability on Windows."""
    if not is_windows():
        return False
    try:
        import importlib

        importlib.import_module("onnxruntime")
        import onnxruntime as ort

        providers = ort.get_available_providers()
        if "DmlExecutionProvider" in providers:
            logger.info("DirectML プロバイダ利用可能")
            return True
    except ImportError:
        logger.debug("onnxruntime が未インストール (DirectML 検出スキップ)")
    except Exception:
        logger.debug("DirectML 検出中にエラー", exc_info=True)
    return False


def _detect_openvino() -> bool:
    """Check if OpenVINO ExecutionProvider is available in ORT."""
    try:
        import onnxruntime as ort
        if "OpenVINOExecutionProvider" in ort.get_available_providers():
            logger.info("OpenVINO プロバイダ利用可能")
            return True
    except ImportError:
        pass
    except Exception:
        logger.debug("OpenVINO 検出中にエラー", exc_info=True)
    return False


def _detect_vitisai() -> bool:
    """Check Vitis AI ExecutionProvider (AMD Ryzen AI NPU) availability."""
    try:
        import onnxruntime as ort

        if "VitisAIExecutionProvider" in ort.get_available_providers():
            logger.info("Vitis AI プロバイダ利用可能 (Ryzen AI NPU)")
            return True
    except ImportError:
        pass
    except Exception:
        logger.debug("Vitis AI 検出中にエラー", exc_info=True)
    return False


def detect_gpu() -> GpuInfo:
    """Detect system GPU and return GpuInfo.

    検出は常に安全に行われ、例外でアプリがクラッシュすることはない。
    """
    info = GpuInfo()

    try:
        # NVIDIA (CUDA) detection
        cuda_ok, nvidia_name = _detect_nvidia()
        if cuda_ok:
            info.cuda_available = True
            info.vendor = "NVIDIA"
            info.name = nvidia_name
            info.recommended_ort_package = "onnxruntime-gpu"
            return info

        # AMD (ROCm) detection — Linux: rocminfo, Windows: HIP SDK
        rocm_ok, amd_name = _detect_rocm()
        if not rocm_ok and is_windows():
            rocm_ok, amd_name = _detect_rocm_windows()
        if rocm_ok:
            info.rocm_available = True
            info.vendor = "AMD"
            info.name = amd_name
            # onnxruntime-rocm has no Windows wheel yet (tracked in TODO)
            info.recommended_ort_package = (
                "onnxruntime" if is_windows() else "onnxruntime-rocm"
            )
            return info

        # AMD Ryzen AI NPU (Vitis AI) detection
        if _detect_vitisai():
            info.vitisai_available = True
            info.vendor = "AMD"
            info.name = "Ryzen AI NPU"
            info.recommended_ort_package = "onnxruntime-vitisai"
            return info

        # Windows DirectML detection
        if is_windows() and _detect_directml():
            info.directml_available = True
            info.vendor = "DirectML"
            info.name = "DirectX 12 GPU"
            info.recommended_ort_package = "onnxruntime-directml"
            return info

        # OpenVINO (Intel NPU) detection
        if _detect_openvino():
            info.openvino_available = True
            info.vendor = "Intel"
            info.name = "OpenVINO NPU"
            info.recommended_ort_package = "onnxruntime-openvino"
            return info

        # macOS CoreML detection
        if is_macos():
            info.coreml_available = True
            info.vendor = "Apple"
            info.name = "CoreML"
            info.recommended_ort_package = "onnxruntime"
            logger.info("macOS 環境: CoreML 利用可能")
            return info

        # When no GPU is found
        logger.info("GPU が検出されなかった (CPU モードで動作)")
        info.recommended_ort_package = "onnxruntime"

    except Exception:
        logger.warning("GPU 検出中に予期しないエラー (CPU フォールバック)", exc_info=True)

    return info
