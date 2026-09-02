"""ORT (ONNX Runtime) provider selection module.

Selects available ExecutionProviders based on priority.
Always returns a safe provider list including CPU fallback.
"""

from __future__ import annotations

import functools
import importlib.metadata
import logging
import threading
import time
from pathlib import Path
from typing import Any

from core.platform import register_nvidia_dll_dirs

from .gpu_detect import detect_gpu

logger = logging.getLogger(__name__)

# In-process registry of active ORT InferenceSessions, keyed by engine name
# (e.g. "wd_tagger", "clip_text", "yolo"). Each entry records the providers
# the session was created with — what `session.get_providers()` reports —
# plus the resolved model path and a registration timestamp. This lets the
# WebUI display "WD-Tagger is currently running on CUDA, CLIP on CPU" so the
# common "I installed onnxruntime-gpu but nothing seems faster" failure mode
# becomes visible at a glance instead of requiring nvidia-smi spelunking.
_active_sessions_lock = threading.Lock()
_active_sessions: dict[str, dict[str, Any]] = {}

# Mutually exclusive onnxruntime PyPI distributions, in detection priority.
# Mirrors scripts/install_onnx.py and pyproject extras.
_ORT_VARIANTS: tuple[str, ...] = (
    "onnxruntime-gpu",
    "onnxruntime-rocm",
    "onnxruntime-directml",
    "onnxruntime-openvino",
    "onnxruntime",
)

# .onnx_extra marker is written at PROJECT_ROOT by start.bat / start.sh /
# scripts/install_onnx.py. Compute the path without depending on a config
# helper so this module stays importable in scripts/CLI contexts too.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ONNX_EXTRA_MARKER = _PROJECT_ROOT / ".onnx_extra"

# Map from extra name (.onnx_extra value) → expected installed variant package
_EXTRA_TO_VARIANT: dict[str, str] = {
    "cpu": "onnxruntime",
    "gpu": "onnxruntime-gpu",
    "directml": "onnxruntime-directml",
    "rocm": "onnxruntime-rocm",
    "silicon": "onnxruntime",
}

# Provider priority: GPU first, CPU last
_PROVIDER_PRIORITY = [
    "CUDAExecutionProvider",
    "ROCmExecutionProvider",
    "VitisAIExecutionProvider",
    "DmlExecutionProvider",
    "OpenVINOExecutionProvider",
    "CoreMLExecutionProvider",
    "CPUExecutionProvider",
]


@functools.cache
def select_providers() -> list[str]:
    """Return available ORT providers in priority order.

    1. NVIDIA DLL ディレクトリを PATH に登録 (Windows)
    2. onnxruntime をインポート
    3. 利用可能なプロバイダを優先順位でフィルタ
    4. CPU フォールバックを常に含める

    Returns:
        選択されたプロバイダ名のリスト
    """
    register_nvidia_dll_dirs()

    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("onnxruntime が未インストール — CPU フォールバック")
        return ["CPUExecutionProvider"]

    available = set(ort.get_available_providers())
    selected = [p for p in _PROVIDER_PRIORITY if p in available]

    if not selected:
        selected = ["CPUExecutionProvider"]

    logger.info("ORT プロバイダ選択: %s (利用可能: %s)", selected, sorted(available))
    return selected


def register_active_session(
    engine_name: str,
    session: Any,
    model_path: str | Path | None = None,
) -> None:
    """Record an ORT InferenceSession in the active-sessions registry.

    Called by each engine right after `ort.InferenceSession(...)` succeeds.
    Failures here must never break inference — engines should call this in a
    try/except that swallows everything (the registry is informational only).
    """
    try:
        providers = list(session.get_providers())
    except Exception:
        providers = []
    entry = {
        "engine": engine_name,
        "providers": providers,
        "active_provider": providers[0] if providers else None,
        "model_path": str(model_path) if model_path else None,
        "registered_at": time.time(),
    }
    with _active_sessions_lock:
        _active_sessions[engine_name] = entry


def unregister_active_session(engine_name: str) -> None:
    """Remove an engine from the registry (e.g. on session disposal)."""
    with _active_sessions_lock:
        _active_sessions.pop(engine_name, None)


def get_active_sessions() -> list[dict[str, Any]]:
    """Return a snapshot of currently registered ORT sessions."""
    with _active_sessions_lock:
        return [dict(entry) for entry in _active_sessions.values()]


def _get_installed_variant() -> str | None:
    """Return the installed onnxruntime variant package name, or None."""
    for variant in _ORT_VARIANTS:
        try:
            importlib.metadata.version(variant)
            return variant
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _read_onnx_extra_marker() -> str | None:
    """Return the contents of `.onnx_extra` (cpu/gpu/directml/rocm), or None."""
    try:
        if not _ONNX_EXTRA_MARKER.exists():
            return None
        val = _ONNX_EXTRA_MARKER.read_text(encoding="utf-8").strip()
        return val if val in _EXTRA_TO_VARIANT else None
    except Exception:
        logger.debug("Failed to read %s", _ONNX_EXTRA_MARKER, exc_info=True)
        return None


def get_provider_info() -> dict:
    """Return GPU info and ORT provider status as a dict.

    Used for API endpoints and debugging.

    Returns:
        available_providers, selected_providers, gpu_info, installed_variant,
        selected_extra, variant_match を含む辞書
    """
    gpu_info = detect_gpu()

    # Get available ORT providers
    available_providers: list[str] = []
    ort_version: str = "not installed"
    try:
        import onnxruntime as ort

        available_providers = list(ort.get_available_providers())
        ort_version = ort.__version__
    except ImportError:
        logger.debug("onnxruntime が未インストール")
    except Exception:
        logger.debug("ORT プロバイダ情報取得中にエラー", exc_info=True)

    # Provider selection
    try:
        selected = select_providers()
    except Exception:
        selected = ["CPUExecutionProvider"]

    # Variant tracking (introduced in v4.128.16 with extras-based onnxruntime).
    # `installed_variant` reflects the actual wheel; `selected_extra` is what
    # the launcher chose; mismatch surfaces "I asked for gpu but ended up with
    # the cpu wheel" — usually means the user manually overrode the marker
    # without re-running `uv sync --extra <variant>`.
    installed_variant = _get_installed_variant()
    selected_extra = _read_onnx_extra_marker()
    expected_variant = _EXTRA_TO_VARIANT.get(selected_extra) if selected_extra else None
    variant_match: bool | None
    if selected_extra is None or installed_variant is None:
        variant_match = None
    else:
        variant_match = installed_variant == expected_variant

    return {
        "ort_version": ort_version,
        "available_providers": available_providers,
        "selected_providers": selected,
        "installed_variant": installed_variant,
        "selected_extra": selected_extra,
        "expected_variant": expected_variant,
        "variant_match": variant_match,
        "active_sessions": get_active_sessions(),
        "gpu_info": {
            "vendor": gpu_info.vendor,
            "name": gpu_info.name,
            "cuda_available": gpu_info.cuda_available,
            "rocm_available": gpu_info.rocm_available,
            "vitisai_available": gpu_info.vitisai_available,
            "directml_available": gpu_info.directml_available,
            "openvino_available": gpu_info.openvino_available,
            "coreml_available": gpu_info.coreml_available,
            "recommended_ort_package": gpu_info.recommended_ort_package,
            "summary": gpu_info.summary(),
        },
    }
