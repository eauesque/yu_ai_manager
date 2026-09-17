"""CLIP encoder initialization and inference logic.

Ported from deploy/hailo_tagger_server_clip.py with InferenceState
replacing module-level globals.
"""

from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

from .state import InferenceState

logger = logging.getLogger(__name__)


def get_clip_encoder(state: InferenceState) -> Any:
    """Lazy-init CLIP image encoder (Hailo > ONNX fallback).

    Uses state._clip_lock for thread-safe initialization.
    Returns the encoder object or None if unavailable.
    """
    if state.get_clip_encoder() is not None:
        return state.get_clip_encoder()

    with state._clip_lock:
        # Double-check after acquiring lock
        if state.get_clip_encoder() is not None:
            return state.get_clip_encoder()

        # Try Hailo first
        enc = _try_clip_hailo()
        if enc is not None:
            state.set_clip_encoder(enc, backend="hailo")
            return state.get_clip_encoder()

        # Fall back to ONNX
        enc = _try_clip_onnx()
        if enc is not None:
            state.set_clip_encoder(enc, backend="onnx")
            return state.get_clip_encoder()

        logger.warning("No CLIP encoder available (tried Hailo, ONNX)")
        return None


def _try_clip_hailo() -> dict | None:
    """Try to initialize Hailo CLIP encoder via shared device manager.

    Uses core.hailo_device_core.device_manager to avoid VDevice conflicts
    with other Hailo consumers (YOLO, tagger, LLM, etc.).
    """
    try:
        from core.hailo_device_core.device_manager import is_hailo_available
        if not is_hailo_available():
            return None
    except ImportError:
        return None

    hef_dir = os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models"))
    hef_path = Path(hef_dir) / "clip_vit_b_16_image_encoder.hef"
    if not hef_path.exists():
        logger.info("Hailo CLIP HEF not found: %s", hef_path)
        return None

    try:
        from core.hailo_device_core.device_manager import acquire_device

        infer_model, _configured, quant_params_list = acquire_device(
            "clip", str(hef_path),
        )
        qp = quant_params_list[0] if quant_params_list else {
            "scale": 1.0, "zero_point": 0.0,
        }

        enc = {
            "type": "hailo",
            "hef_path": str(hef_path),
            "input_shape": tuple(infer_model.inputs[0].shape),
            "output_shape": tuple(infer_model.outputs[0].shape),
            "scale": qp["scale"],
            "zero_point": qp["zero_point"],
        }
        logger.info(
            "CLIP encoder loaded: Hailo-10H (%s, scale=%.6f, zp=%.1f)",
            hef_path, qp["scale"], qp["zero_point"],
        )
        return enc
    except Exception as exc:
        logger.warning("Hailo CLIP init failed: %s", exc)
        return None


def _download_clip_onnx(cache_dir: Path) -> Path | None:
    """Download CLIP ViT-B/16 ONNX vision model from HuggingFace."""
    repo = "Xenova/clip-vit-base-patch16"
    model_dir = cache_dir / re.sub(r"[^\w\-.]", "_", repo)
    model_dir.mkdir(parents=True, exist_ok=True)
    dest = model_dir / "vision_model.onnx"
    if dest.exists():
        return dest

    url = f"https://huggingface.co/{repo}/resolve/main/onnx/vision_model.onnx"
    logger.info("CLIP ONNX: downloading from %s ...", url)
    tmp = dest.with_suffix(".onnx.tmp")
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "YuAiManager/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        tmp.rename(dest)
        logger.info(
            "CLIP ONNX: downloaded (%.1f MB)", dest.stat().st_size / (1024 * 1024)
        )
        return dest
    except Exception as exc:
        logger.warning("CLIP ONNX: download failed: %s", exc)
        if tmp.exists():
            tmp.unlink()
        return None


def _try_clip_onnx() -> Any:
    """Try to initialize ONNX CLIP encoder. Returns session or None."""
    try:
        import onnxruntime as ort
    except Exception as exc:
        logger.warning("CLIP ONNX: onnxruntime import failed: %s", exc)
        return None

    from .engines import OnnxEngine

    cache_dir = Path.home() / ".cache" / "yu_ai_manager" / "clip_onnx"
    model_path = None
    if cache_dir.exists():
        for subdir in cache_dir.iterdir():
            candidate = subdir / "vision_model.onnx"
            if candidate.exists():
                model_path = candidate
                break
    if model_path is None:
        model_path = _download_clip_onnx(cache_dir)
        if model_path is None:
            return None
    try:
        providers = OnnxEngine.select_providers()
        logger.info("CLIP ONNX: trying providers %s for %s", providers, model_path)
        session = ort.InferenceSession(str(model_path), providers=providers)
        active = session.get_providers()[0] if session.get_providers() else "CPU"
        logger.info("CLIP encoder loaded: ONNX (%s, provider=%s)", model_path, active)
        try:
            from extensions.builtin_inference.core_impl.ort_provider import register_active_session
            register_active_session("lan_cowork_clip", session, model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)
        return session
    except Exception as exc:
        logger.warning("ONNX CLIP init failed: %s", exc, exc_info=True)
        return None


def preprocess_clip_image(image_data: bytes, backend: str) -> np.ndarray:
    """Preprocess image bytes for CLIP. Format depends on backend.

    Args:
        image_data: Raw image bytes (JPEG/PNG/etc).
        backend: "hailo" or "onnx" — determines output format.

    Returns:
        numpy array ready for encoder input.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    img = img.resize((224, 224), Image.LANCZOS)

    if backend == "hailo":
        return np.array(img, dtype=np.uint8)

    # ONNX path: normalize with CLIP mean/std, NCHW layout
    arr = np.array(img, dtype=np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
    std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)
    return np.expand_dims(arr, 0).astype(np.float32)


def clip_encode_single(
    encoder: Any, preprocessed: np.ndarray, backend: str
) -> np.ndarray:
    """Run CLIP encode, return L2-normalized (512,) float32.

    Args:
        encoder: Encoder dict (Hailo) or InferenceSession (ONNX).
        preprocessed: Output of preprocess_clip_image().
        backend: "hailo" or "onnx".

    Returns:
        Unit-normalized float32 vector of shape (512,).
    """
    if backend == "hailo":
        from core.hailo_device_core.device_manager import acquire_device

        infer_model, configured, quant_params_list = acquire_device(
            "clip", encoder["hef_path"],
        )
        qp = quant_params_list[0] if quant_params_list else {
            "scale": encoder["scale"], "zero_point": encoder["zero_point"],
        }
        output_shape = tuple(infer_model.outputs[0].shape)
        output_buf = np.empty(output_shape, dtype=np.uint8)
        bindings = configured.create_bindings()
        bindings.input().set_buffer(preprocessed)
        bindings.output().set_buffer(output_buf)
        configured.run([bindings], timeout=10000)
        vec = (
            output_buf.flatten().astype(np.float32) - qp["zero_point"]
        ) * qp["scale"]
    else:
        input_name = encoder.get_inputs()[0].name
        vec = encoder.run(None, {input_name: preprocessed})[0][0]

    norm = np.linalg.norm(vec)
    if norm > 1e-12:
        vec = vec / norm
    return vec.astype(np.float32)
