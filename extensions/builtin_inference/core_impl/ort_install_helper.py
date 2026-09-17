"""ORT installation helper CLI.

Detects GPU and displays recommended onnxruntime package and install command.

Usage:
    python -m core.inference_core.ort_install_helper
"""

from __future__ import annotations

import logging

from .gpu_detect import detect_gpu

logger = logging.getLogger(__name__)

# Package name to install command mapping
_INSTALL_COMMANDS = {
    "onnxruntime-gpu": "uv pip install onnxruntime-gpu",
    "onnxruntime-rocm": "uv pip install onnxruntime-rocm",
    "onnxruntime-vitisai": (
        "Ryzen AI Software をインストール "
        "(https://ryzenai.docs.amd.com/en/latest/inst.html)"
    ),
    "onnxruntime-directml": "uv pip install onnxruntime-directml",
    "onnxruntime-openvino": "uv pip install onnxruntime-openvino",
    "onnxruntime": "uv pip install onnxruntime",
}

# Package descriptions
_PACKAGE_DESCRIPTIONS = {
    "onnxruntime-gpu": "NVIDIA CUDA GPU アクセラレーション",
    "onnxruntime-rocm": "AMD ROCm GPU アクセラレーション",
    "onnxruntime-vitisai": "AMD Ryzen AI NPU アクセラレーション (Vitis AI)",
    "onnxruntime-directml": "Windows DirectML GPU アクセラレーション",
    "onnxruntime-openvino": "Intel OpenVINO NPU アクセラレーション",
    "onnxruntime": "CPU のみ (GPU アクセラレーションなし)",
}


def get_recommendation() -> dict:
    """Return recommended package info based on GPU information.

    Returns:
        gpu_info, recommended_package, install_command,
        description を含む辞書
    """
    gpu_info = detect_gpu()
    pkg = gpu_info.recommended_ort_package
    return {
        "gpu_info": {
            "vendor": gpu_info.vendor,
            "name": gpu_info.name,
            "cuda_available": gpu_info.cuda_available,
            "rocm_available": gpu_info.rocm_available,
            "vitisai_available": gpu_info.vitisai_available,
            "directml_available": gpu_info.directml_available,
            "coreml_available": gpu_info.coreml_available,
            "summary": gpu_info.summary(),
        },
        "recommended_package": pkg,
        "install_command": _INSTALL_COMMANDS.get(pkg, f"uv pip install {pkg}"),
        "description": _PACKAGE_DESCRIPTIONS.get(pkg, ""),
    }


def _check_current_install() -> str | None:
    """Check the currently installed onnxruntime package."""
    try:
        import onnxruntime as ort

        return ort.__version__
    except ImportError:
        return None


def main() -> None:
    """Display GPU detection results and recommended install command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("  ORT (ONNX Runtime) GPU 検出 & インストールヘルパー")
    logger.info("=" * 60)

    rec = get_recommendation()
    gpu = rec["gpu_info"]

    logger.info(f"  GPU: {gpu['summary']}")
    logger.info("  検出結果:")
    logger.info(f"    CUDA:     {'OK' if gpu['cuda_available'] else '--'}")
    logger.info(f"    ROCm:     {'OK' if gpu['rocm_available'] else '--'}")
    logger.info(f"    Vitis AI: {'OK' if gpu.get('vitisai_available') else '--'}")
    logger.info(f"    DirectML: {'OK' if gpu['directml_available'] else '--'}")
    logger.info(f"    CoreML:   {'OK' if gpu['coreml_available'] else '--'}")

    # Current installation status
    current = _check_current_install()
    if current:
        logger.info(f"  現在の onnxruntime: v{current}")
    else:
        logger.info("  現在の onnxruntime: 未インストール")

    # Recommended package
    logger.info(f"  推奨パッケージ: {rec['recommended_package']}")
    logger.info(f"  説明: {rec['description']}")
    logger.info("  インストールコマンド:")
    logger.info(f"    {rec['install_command']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
