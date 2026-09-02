"""Whisper Hailo NPU pipeline helpers for standalone deployment."""

from __future__ import annotations

import logging

import numpy as np
from whisper_hailo_decoder import init_decoder_hailo, run_decoder_hailo
from whisper_hailo_pipeline import WhisperHailoPipeline
from whisper_hailo_support import _CACHE_DIR, _DECODER_URL, _ENCODER_URL, download_file

logger = logging.getLogger(__name__)


def _init_encoder(model_size: str = "base") -> object | None:
    """Download and load Whisper encoder ONNX model."""
    try:
        import onnxruntime as ort
    except ImportError:
        logger.error("onnxruntime not installed")
        return None

    encoder_path = _CACHE_DIR / f"encoder_{model_size}.onnx"
    if not encoder_path.exists() and not download_file(_ENCODER_URL, encoder_path, f"whisper-{model_size} encoder"):
        return None

    try:
        session = ort.InferenceSession(str(encoder_path), providers=["CPUExecutionProvider"])
        logger.info("Whisper encoder loaded: %s", encoder_path.name)
        return session
    except Exception as exc:
        logger.error("Whisper encoder init failed: %s", exc)
        return None


def run_encoder(session, mel: np.ndarray) -> np.ndarray | None:
    """Run Whisper encoder and return the first 500 hidden frames."""
    input_info = session.get_inputs()[0]
    expected_frames = input_info.shape[-1] if isinstance(input_info.shape[-1], int) else 3000
    if mel.shape[1] < expected_frames:
        mel = np.pad(mel, ((0, 0), (0, expected_frames - mel.shape[1])))
    elif mel.shape[1] > expected_frames:
        mel = mel[:, :expected_frames]

    try:
        features = session.run(None, {input_info.name: mel[np.newaxis].astype(np.float32)})[0]
        return features[:, :500, :] if features.shape[1] > 500 else features
    except Exception as exc:
        logger.error("Encoder inference failed: %s", exc)
        return None


def _extract_embed_weights(model_size: str = "base") -> np.ndarray | None:
    """Extract token embedding weights from the decoder ONNX model."""
    try:
        import onnxruntime as ort
    except ImportError:
        return None

    decoder_path = _CACHE_DIR / f"decoder_{model_size}.onnx"
    if not decoder_path.exists() and not download_file(_DECODER_URL, decoder_path, f"whisper-{model_size} decoder"):
        return None

    try:
        import onnx

        model = onnx.load(str(decoder_path))
        for initializer in model.graph.initializer:
            if "embed_tokens" in initializer.name or (
                "embed_positions" not in initializer.name and "embed" in initializer.name
            ):
                weight = np.frombuffer(initializer.raw_data, dtype=np.float32).reshape(initializer.dims)
                if weight.shape[-1] == 512 and weight.shape[0] > 50000:
                    logger.info("Extracted embed_tokens: %s", weight.shape)
                    return weight
        logger.warning("embed_tokens not found in decoder ONNX")
        return None
    except ImportError:
        logger.info("onnx package not available, extracting embeddings via dummy inference")
        try:
            ort.InferenceSession(str(decoder_path), providers=["CPUExecutionProvider"])
            embed_path = _CACHE_DIR / f"embed_tokens_{model_size}.npy"
            if embed_path.exists():
                weights = np.load(str(embed_path))
                logger.info("Loaded cached embed_tokens: %s", weights.shape)
                return weights
            logger.warning("Cannot extract embeddings without onnx package. Install: pip install onnx")
            return None
        except Exception as exc:
            logger.warning("Embedding extraction fallback failed: %s", exc)
            return None
    except Exception as exc:
        logger.error("Embedding extraction failed: %s", exc)
        return None


def init_encoder_session(model_size: str = "base") -> object | None:
    return _init_encoder(model_size)


def run_encoder_features(session, mel: np.ndarray) -> np.ndarray | None:
    return run_encoder(session, mel)


def build_onnx_decoder_engine(hef_path: str, model_size: str = "base") -> dict | None:
    """Build the fallback decoder engine for ONNX/CPU transcription."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        embed_weights = _extract_embed_weights(model_size)
    except Exception as exc:
        logger.warning("Could not extract embeddings: %s", exc)
        embed_weights = None

    decoder_path = _CACHE_DIR / f"decoder_{model_size}.onnx"
    if not decoder_path.exists():
        hf_base = f"https://huggingface.co/onnx-community/whisper-{model_size}/resolve/main/onnx"
        if not download_file(f"{hf_base}/decoder_model.onnx", decoder_path, f"whisper-{model_size} decoder"):
            return None

    try:
        from hailo_platform import HEF

        hef = HEF(hef_path)
        inputs = hef.get_input_vstream_infos()
        d_model = 768 if model_size == "small" else 512
        max_tokens = 64
        for info in inputs:
            if info.shape[1] == 64:
                max_tokens = info.shape[1]
                d_model = info.shape[2]
    except Exception:
        d_model = 768 if model_size == "small" else 512
        max_tokens = 64

    return {
        "hef_path": hef_path,
        "d_model": d_model,
        "max_tokens": max_tokens,
        "embed_weights": embed_weights,
        "_model_size": model_size,
        "network_group": None,
    }


__all__ = [
    "WhisperHailoPipeline",
    "build_onnx_decoder_engine",
    "init_decoder_hailo",
    "init_encoder_session",
    "run_decoder_hailo",
    "run_encoder_features",
]
