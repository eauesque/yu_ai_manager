"""YOLO backend initialisation helpers."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from .state import YOLO_INIT_COOLDOWN, InferenceState
from .yolo_models import YOLO_ONNX_MODELS

logger = logging.getLogger(__name__)


def get_yolo_engine(state: InferenceState) -> Any:
    """Lazy-init YOLO detector (Hailo > ONNX) with cooldown on failure."""
    if state.get_yolo_engine() is not None:
        return state.get_yolo_engine()

    failed_ts = state.get_yolo_init_failed()
    if failed_ts and (time.time() - failed_ts) < YOLO_INIT_COOLDOWN:
        return None

    with state._yolo_lock:
        if state.get_yolo_engine() is not None:
            return state.get_yolo_engine()

        engine = _try_yolo_hailo()
        if engine is not None:
            state.set_yolo_engine(engine, input_size=engine["input_size"])
            return state.get_yolo_engine()

        engine = _try_yolo_onnx()
        if engine is not None:
            state.set_yolo_engine(engine, input_size=engine["input_size"])
            return state.get_yolo_engine()

        logger.warning(
            "No YOLO engine available (tried Hailo, ONNX) -- retry in %ds",
            int(YOLO_INIT_COOLDOWN),
        )
        state.set_yolo_init_failed(time.time())
        return None


def _try_yolo_hailo() -> dict | None:
    try:
        from core.hailo_device_core.device_manager import is_hailo_available

        if not is_hailo_available():
            logger.info("YOLO Hailo: hailo_platform not available")
            return None
    except ImportError:
        logger.info("YOLO Hailo: hailo_platform not available")
        return None

    hef_dir = os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models"))
    candidates = [
        ("yolov8n", "yolov8n.hef", 640),
        ("yolov11n", "yolov11n.hef", 640),
        ("yolov5m", "yolov5m_wo_spp.hef", 640),
    ]
    hef_path: Path | None = None
    model_name = ""
    input_size = 640
    for name, filename, size in candidates:
        candidate = Path(hef_dir) / filename
        if candidate.exists() and hef_path is None:
            hef_path = candidate
            model_name = name
            input_size = size

    if hef_path is None:
        logger.warning("No YOLO HEF found in %s", hef_dir)
        return None

    logger.info("YOLO Hailo: loading %s from %s", model_name, hef_path)
    try:
        from core.hailo_device_core.device_manager import acquire_device

        infer_model, _configured, quant_params_list = acquire_device("lan-yolo", str(hef_path))
        has_nms = any("nms" in out.name.lower() for out in infer_model.outputs)
        output_shapes = [tuple(out.shape) for out in infer_model.outputs]

        engine = {
            "type": "hailo",
            "model_name": model_name,
            "input_size": input_size,
            "hef_path": str(hef_path),
            "has_nms": has_nms,
        }
        logger.info(
            "YOLO detector loaded: Hailo-10H %s (%s), %d outputs, nms=%s",
            model_name,
            hef_path,
            len(output_shapes),
            has_nms,
        )
        for idx, qp in enumerate(quant_params_list):
            logger.info(
                "  Output %d: %s shape=%s scale=%.6f zp=%.1f",
                idx,
                qp["name"],
                qp["shape"],
                qp["scale"],
                qp["zero_point"],
            )
        return engine
    except Exception as exc:
        logger.warning("Hailo YOLO init failed: %s", exc)
        return None


def _try_yolo_onnx() -> dict | None:
    try:
        import onnxruntime as ort
    except ImportError:
        logger.info("YOLO ONNX: onnxruntime not available")
        return None

    from .engines import OnnxEngine

    cache_dir = Path.home() / ".cache" / "yu_ai_manager" / "yolo_onnx"
    cache_dir.mkdir(parents=True, exist_ok=True)

    for model_name, info in YOLO_ONNX_MODELS.items():
        model_path = cache_dir / info["filename"]
        if not model_path.exists():
            logger.info("YOLO ONNX: downloading %s...", model_name)
            try:
                import urllib.request

                req = urllib.request.Request(
                    info["url"], headers={"User-Agent": "YuAiManager/1.0"}
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    model_path.write_bytes(resp.read())
                logger.info(
                    "YOLO ONNX: downloaded %s (%d bytes)",
                    model_name,
                    model_path.stat().st_size,
                )
            except Exception as exc:
                logger.warning("YOLO ONNX: download failed for %s: %s", model_name, exc)
                continue

        try:
            providers = OnnxEngine.select_providers()
            session = ort.InferenceSession(str(model_path), providers=providers)
            active = session.get_providers()[0] if session.get_providers() else "CPU"
            logger.info("YOLO ONNX: loaded %s (provider=%s)", model_name, active)
            try:
                from extensions.builtin_inference.core_impl.ort_provider import register_active_session
                register_active_session(f"yolo_{model_name}", session, model_path)
            except Exception:
                logger.debug("ORT session registry update failed", exc_info=True)
            return {
                "type": "onnx",
                "model_name": model_name,
                "input_size": info["input_size"],
                "session": session,
            }
        except Exception as exc:
            logger.warning("YOLO ONNX: failed to load %s: %s", model_name, exc)
    return None
