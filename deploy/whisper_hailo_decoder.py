"""Decoder helpers for the standalone Whisper Hailo pipeline."""

from __future__ import annotations

import logging

import numpy as np
from whisper_hailo_support import _CACHE_DIR, EOT, LANG_TOKENS, NO_TIMESTAMPS, SOT, TRANSCRIBE

logger = logging.getLogger(__name__)


def init_decoder_hailo(hef_path: str, embed_weights: np.ndarray | None = None) -> dict | None:
    """Initialize Hailo NPU decoder with VDevice + configured model."""
    try:
        from hailo_platform import HEF, FormatType, InputVStreamParams, OutputVStreamParams, VDevice
    except ImportError:
        logger.error("hailo_platform not available")
        return None

    hef = HEF(hef_path)
    inputs = list(hef.get_input_vstream_infos())
    outputs = list(hef.get_output_vstream_infos())
    logger.info("Whisper HEF: %s", hef_path)
    for info in inputs:
        logger.info("  Input:  %s shape=%s", info.name, info.shape)
    for info in outputs:
        logger.info("  Output: %s shape=%s", info.name, info.shape)

    encoder_input = None
    token_input = None
    for info in inputs:
        if info.shape[1] == 500:
            encoder_input = info
        elif info.shape[1] == 64:
            token_input = info
    if encoder_input is None or token_input is None:
        logger.error("Cannot identify encoder/token inputs from shapes")
        return None

    try:
        vdevice = VDevice()
        network_group = vdevice.configure(hef)[0]
        return {
            "hef_path": hef_path,
            "encoder_input_name": encoder_input.name,
            "token_input_name": token_input.name,
            "d_model": token_input.shape[2],
            "max_tokens": token_input.shape[1],
            "output_infos": outputs,
            "embed_weights": embed_weights,
            "_model_size": "small" if token_input.shape[2] == 768 else "base",
            "vdevice": vdevice,
            "network_group": network_group,
            "input_vstream_params": InputVStreamParams.make(network_group, format_type=FormatType.FLOAT32),
            "output_vstream_params": OutputVStreamParams.make(network_group, format_type=FormatType.FLOAT32),
        }
    except Exception as exc:
        logger.error("Hailo Whisper decoder init failed: %s", exc)
        return None


def run_decoder_onnx_fallback(engine: dict, encoder_features: np.ndarray, language: str = "ja") -> list[int]:
    """Run Whisper decoder on ONNX/CPU when Hailo VDevice is unavailable."""
    try:
        import onnxruntime as ort
    except ImportError:
        logger.error("onnxruntime not available for decoder fallback")
        return []

    decoder_path = _CACHE_DIR / f"decoder_{engine.get('_model_size', 'base')}.onnx"
    if not decoder_path.exists():
        logger.error("Decoder ONNX not found: %s", decoder_path)
        return []

    try:
        session = ort.InferenceSession(str(decoder_path), providers=["CPUExecutionProvider"])
        input_names = [inp.name for inp in session.get_inputs()]
        lang_token = LANG_TOKENS.get(language, LANG_TOKENS["en"])
        enc_feat = encoder_features.astype(np.float32)
        if enc_feat.ndim == 2:
            enc_feat = enc_feat[np.newaxis]

        all_tokens = [SOT, lang_token, TRANSCRIBE, NO_TIMESTAMPS]
        for _ in range(engine["max_tokens"] - len(all_tokens)):
            input_ids = np.array([all_tokens], dtype=np.int64)
            feed = {}
            for name in input_names:
                if "encoder" in name.lower() or "hidden" in name.lower():
                    feed[name] = enc_feat
                elif "input_ids" in name.lower() or "decoder" in name.lower():
                    feed[name] = input_ids
            if len(feed) < 2:
                logger.warning("ONNX decoder fallback: unable to map inputs (%s)", input_names)
                break
            try:
                next_token = int(session.run(None, feed)[0][0, -1].argmax())
                if next_token == EOT:
                    break
                all_tokens.append(next_token)
            except Exception as exc:
                logger.warning("ONNX decoder step failed: %s", exc)
                break
        return [token for token in all_tokens if token < 50257]
    except Exception as exc:
        logger.error("ONNX decoder fallback failed: %s", exc)
        return []


def run_decoder_hailo(engine: dict, encoder_features: np.ndarray, language: str = "ja", vdevice=None) -> list[int]:
    """Run Hailo decoder on encoder features."""
    embed_weights = engine["embed_weights"]
    lang_token = LANG_TOKENS.get(language, LANG_TOKENS["en"])
    prompt_ids = [SOT, lang_token, TRANSCRIBE, NO_TIMESTAMPS]
    while len(prompt_ids) < engine["max_tokens"]:
        prompt_ids.append(EOT)

    if embed_weights is not None:
        token_embeds = embed_weights[prompt_ids][np.newaxis].astype(np.float32)
    else:
        logger.warning("Using fallback token embeddings (no embed_weights)")
        token_embeds = np.zeros((1, engine["max_tokens"], engine["d_model"]), dtype=np.float32)
        for i, token_id in enumerate(prompt_ids):
            np.random.seed(token_id)
            token_embeds[0, i] = np.random.randn(engine["d_model"]).astype(np.float32) * 0.02

    enc_feat = encoder_features.astype(np.float32)
    if enc_feat.shape[0] != 1:
        enc_feat = enc_feat[np.newaxis]

    try:
        from hailo_platform import InferVStreams

        if engine.get("network_group") is None:
            logger.warning("Hailo decoder not configured, falling back to ONNX")
            return run_decoder_onnx_fallback(engine, encoder_features, language)

        input_data = {
            engine["encoder_input_name"]: enc_feat,
            engine["token_input_name"]: token_embeds,
        }
        with InferVStreams(
            engine["network_group"],
            engine["input_vstream_params"],
            engine["output_vstream_params"],
        ) as pipeline:
            results = pipeline.infer(input_data)
        if not results:
            logger.error("No decoder output buffers")
            return []

        dequantized = [results[name].astype(np.float32) for name in sorted(results.keys())]
        raw_output = np.concatenate(dequantized, axis=-1) if len(dequantized) > 1 else dequantized[0]
        if raw_output.ndim == 3:
            token_ids = raw_output[0].argmax(axis=-1).tolist()
        elif raw_output.ndim == 2:
            token_ids = raw_output[0].astype(int).tolist()
        elif raw_output.ndim == 1:
            token_ids = raw_output.astype(int).tolist()
        else:
            logger.error("Unexpected decoder output shape: %s", raw_output.shape)
            return []

        result = []
        for token_id in token_ids:
            if token_id == EOT:
                break
            if token_id < 50257:
                result.append(token_id)
        return result
    except Exception as exc:
        logger.error("Hailo decoder inference failed: %s", exc)
        return []
