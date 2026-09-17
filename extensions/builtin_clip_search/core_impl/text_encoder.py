"""CLIP text encoder for semantic search queries — ONNX runtime backend.

Uses ``onnxruntime`` + the ``tokenizers`` library, sharing the same
``Xenova/clip-vit-base-patch16`` repo as the vision encoder. The Xenova
export bakes ``text_projection`` into ``text_model.onnx``, so the single
output is the 512-dim text embedding (matches the vision side's
``output_dim``). Indexing is unaffected — text encoding only runs once per
search query, so CPU is sufficient and we don't pay the multi-GB
PyTorch dependency cost.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_session: object | None = None  # onnxruntime.InferenceSession
_tokenizer: object | None = None  # tokenizers.Tokenizer
_input_names: list[str] = []
_output_name: str = ""

# CLIP token sequence length (see openai/clip-vit-base-patch16 config).
_MAX_LEN = 77


def _load_model() -> None:
    """Lazy-load the ONNX session and BPE tokenizer (thread-safe)."""
    global _session, _tokenizer, _input_names, _output_name
    if _session is not None and _tokenizer is not None:
        return

    with _lock:
        if _session is not None and _tokenizer is not None:
            return

        logger.info("Loading CLIP text encoder (ONNX, first use)...")

        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise ImportError(
                "onnxruntime and tokenizers are required for text encoding. "
                "Run: uv sync"
            ) from exc

        from core.clip_onnx_core.text_model_download import (
            download_text_model,
            is_text_model_downloaded,
            resolve_existing_text_model_path,
            resolve_existing_tokenizer_path,
        )

        if not is_text_model_downloaded():
            logger.info("CLIP ONNX text model not cached — downloading...")
            download_text_model()

        model_path = resolve_existing_text_model_path()
        tok_path = resolve_existing_tokenizer_path()
        if model_path is None or tok_path is None:
            raise RuntimeError(
                "CLIP ONNX text model + tokenizer download did not produce expected files"
            )

        # Match the vision side's provider selection so both encoders use the
        # same hardware (NPU/GPU when available, CPU fallback otherwise).
        try:
            from importlib import import_module
            _ort_mod = import_module(
                "extensions.builtin_inference.core_impl.ort_provider"
            )
            providers = _ort_mod.select_providers()
        except Exception:
            providers = ["CPUExecutionProvider"]

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(
            str(model_path), sess_options=sess_opts, providers=providers,
        )
        _input_names = [inp.name for inp in _session.get_inputs()]
        _output_name = _session.get_outputs()[0].name

        _tokenizer = Tokenizer.from_file(str(tok_path))
        _tokenizer.enable_truncation(max_length=_MAX_LEN)
        _tokenizer.enable_padding(length=_MAX_LEN, pad_id=0, pad_token="<|endoftext|>")

        active_providers = _session.get_providers()
        provider = active_providers[0] if active_providers else "CPUExecutionProvider"
        logger.info(
            "CLIP text encoder loaded: %s (provider: %s, output: %s)",
            model_path.name, provider, _output_name,
        )
        try:
            from extensions.builtin_inference.core_impl.ort_provider import register_active_session
            register_active_session("clip_text", _session, model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)


def encode_text(text: str) -> np.ndarray:
    """Encode a text query to a CLIP embedding vector.

    Args:
        text: search query string.

    Returns:
        ``(512,)`` float32 L2-normalized vector.
    """
    _load_model()

    enc = _tokenizer.encode(text)  # type: ignore[union-attr]
    input_ids = np.array([enc.ids], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)

    feeds: dict[str, np.ndarray] = {}
    for name in _input_names:
        if name == "input_ids":
            feeds[name] = input_ids
        elif name == "attention_mask":
            feeds[name] = attention_mask
        # Ignore any other inputs the export might define (e.g. position_ids
        # are auto-derived in CLIP text models).

    outputs = _session.run([_output_name], feeds)  # type: ignore[union-attr]
    vec = np.asarray(outputs[0]).flatten().astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 1e-12:
        vec = vec / norm
    return vec


def is_text_encoder_available() -> bool:
    """Check that runtime deps + the downloaded model files are both present."""
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    try:
        from core.clip_onnx_core.text_model_download import is_text_model_downloaded
        return is_text_model_downloaded()
    except Exception:
        return False


def get_text_encoder_info() -> dict:
    """Return info about the text encoder status (for /api/status)."""
    deps_ok = True
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        deps_ok = False

    model_ready = False
    model_path: str | None = None
    try:
        from core.clip_onnx_core.text_model_download import (
            get_text_model_status,
        )
        status = get_text_model_status()
        model_ready = status["ready"]
        model_path = status["path"] if status["ready"] else None
    except Exception:
        logger.warning("text model status was unreadable", exc_info=True)

    available = deps_ok and model_ready
    return {
        "available": available,
        "loaded": _session is not None and _tokenizer is not None,
        "model": "Xenova/clip-vit-base-patch16 (text_model.onnx)" if available else None,
        "model_path": model_path,
        "deps_ok": deps_ok,
        "model_downloaded": model_ready,
        "backend": "onnx",
    }
