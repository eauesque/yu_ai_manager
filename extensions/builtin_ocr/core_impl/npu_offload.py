"""3d: NPU offload -- utilize Hailo / Ryzen AI NPU for OCR inference.

Offloads VLM inference to NPU when available.
Transparently falls back to CPU/GPU when unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NpuStatus:
    """NPU availability and status."""
    hailo_available: bool = False
    hailo_device: str = ""
    hailo_driver_version: str = ""
    ryzen_available: bool = False
    ryzen_npu_name: str = ""
    preferred_backend: str = "auto"  # auto, hailo, ryzen, cpu

    def to_dict(self) -> dict[str, Any]:
        return {
            "hailo_available": self.hailo_available,
            "hailo_device": self.hailo_device,
            "hailo_driver_version": self.hailo_driver_version,
            "ryzen_available": self.ryzen_available,
            "ryzen_npu_name": self.ryzen_npu_name,
            "preferred_backend": self.preferred_backend,
            "any_npu_available": self.hailo_available or self.ryzen_available,
        }


def detect_npu() -> NpuStatus:
    """Detect available NPU devices."""
    status = NpuStatus()

    # Hailo detection
    status.hailo_available, status.hailo_device, status.hailo_driver_version = (
        _detect_hailo()
    )

    # Ryzen AI NPU detection
    status.ryzen_available, status.ryzen_npu_name = _detect_ryzen()

    # Auto-select
    if status.hailo_available:
        status.preferred_backend = "hailo"
    elif status.ryzen_available:
        status.preferred_backend = "ryzen"
    else:
        status.preferred_backend = "cpu"

    return status


def _detect_hailo() -> tuple[bool, str, str]:
    """Detect Hailo devices without acquiring the VDevice.

    Uses is_hailo_available() (import-only check) to avoid conflicts
    with other Hailo consumers sharing the single VDevice.
    """
    try:
        from core.hailo_device_core.device_manager import is_hailo_available
        if is_hailo_available():
            return True, "Hailo-10H", ""
        return False, "", ""
    except ImportError:
        return False, "", ""
    except Exception as exc:
        logger.debug("Hailo detection failed: %s", exc)
        return False, "", ""


def _detect_ryzen() -> tuple[bool, str]:
    """Detect AMD Ryzen AI NPU."""
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "VitisAIExecutionProvider" in providers:
            return True, "Ryzen AI (Vitis AI)"
        # NPU access via DirectML (Windows)
        if "DmlExecutionProvider" in providers:
            return True, "Ryzen AI (DirectML)"
        return False, ""
    except ImportError:
        return False, ""
    except Exception as exc:
        logger.debug("Ryzen AI detection failed: %s", exc)
        return False, ""


def get_npu_ocr_server_id(
    config: dict | None = None,
) -> str | None:
    """Return NPU-based OCR server ID (if available).

    サーバーレジストリから hailo_vlm タイプのサーバーを探す。
    """
    from core.analysis_api.server_registry import get_all_servers
    from core.configuration.api import load_config_json

    if config is None:
        config = load_config_json(None)

    servers = get_all_servers(config)
    for srv in servers:
        if not srv.enabled:
            continue
        if srv.type == "hailo_vlm":
            return srv.id
    return None


def suggest_npu_optimization(
    task: str = "ocr",
) -> dict[str, Any]:
    """Return recommended settings for NPU offload."""
    status = detect_npu()

    if not status.hailo_available and not status.ryzen_available:
        return {
            "available": False,
            "message": "NPU が検出されませんでした",
            "recommendations": [
                "Hailo-10H: M.2 スロットに装着し hailort ドライバをインストール",
                "Ryzen AI: AMD NPU ドライバと ONNX Runtime Vitis AI EP をインストール",
            ],
        }

    recommendations = []

    if status.hailo_available:
        npu_server = get_npu_ocr_server_id()
        if npu_server:
            recommendations.append(
                f"Hailo VLM サーバー '{npu_server}' が利用可能です。"
                f" server_id='{npu_server}' を指定して OCR を実行できます。"
            )
        else:
            recommendations.append(
                "Hailo デバイスは検出されましたが、サーバーレジストリに "
                "hailo_vlm タイプのサーバーが登録されていません。"
                " AI Settings で hailo_vlm サーバーを追加してください。"
            )

    if status.ryzen_available:
        recommendations.append(
            f"Ryzen AI NPU ({status.ryzen_npu_name}) が利用可能です。"
            " ONNX Runtime ベースの推論で自動的に活用されます。"
        )

    return {
        "available": True,
        "status": status.to_dict(),
        "task": task,
        "recommendations": recommendations,
    }
