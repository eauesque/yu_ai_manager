"""ONNX Runtime backend session.

Loads an ONNX model and runs inference. Provider selection is delegated
to the existing ort_provider helper for consistency with engine_onnx.py.

Spec § 4.1 (backends/onnx_backend.py).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .base import BackendSession

logger = logging.getLogger(__name__)


def _select_providers() -> list[str]:
    """Delegate provider selection to existing ort_provider helper."""
    from importlib import import_module

    mod = import_module("extensions.builtin_inference.core_impl.ort_provider")
    return mod.select_providers()


class OnnxBackendSession(BackendSession):
    """ONNX Runtime InferenceSession wrapper."""

    def __init__(self, model_path: str | Path):
        self._model_path = Path(model_path)
        self._session: object | None = None
        self._input_name: str | None = None
        self._load()

    def _load(self) -> None:
        if not self._model_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {self._model_path}")

        providers = _select_providers()
        import onnxruntime as ort

        logger.info(
            "Loading ONNX model from %s (providers: %s)",
            self._model_path,
            providers,
        )
        self._session = ort.InferenceSession(
            str(self._model_path),
            providers=providers,
        )
        active = self._session.get_providers()  # type: ignore[union-attr]
        logger.info("ONNX session active providers: %s", active)
        self._input_name = self._session.get_inputs()[0].name  # type: ignore[union-attr]

        # Register session with the shared ORT session registry so GPU
        # diagnostics tools (cuDNN logs, provider stats) can find it.
        # Failure here is non-fatal — match legacy engine_onnx behavior.
        try:
            from extensions.builtin_inference.core_impl.ort_provider import (
                register_active_session,
            )
            register_active_session("wd_tagger", self._session, self._model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)

    def get_input_name(self) -> str:
        if self._input_name is None:
            raise RuntimeError("session not loaded")
        return self._input_name

    def run(
        self,
        input_array: np.ndarray,
        output_key: str | None = None,
    ) -> np.ndarray:
        if self._session is None:
            raise RuntimeError("session not loaded")
        outputs = self._session.run(None, {self._input_name: input_array})  # type: ignore[union-attr]
        if output_key is None:
            return outputs[0]
        names = [o.name for o in self._session.get_outputs()]  # type: ignore[union-attr]
        try:
            index = names.index(output_key)
        except ValueError:
            raise ValueError(
                f"output_spec.output_key={output_key!r} not among model outputs {names}"
            ) from None
        return outputs[index]

    def is_loaded(self) -> bool:
        return self._session is not None

    def close(self) -> None:
        # onnxruntime InferenceSession does not have an explicit close;
        # rely on GC. We just drop the reference.
        self._session = None
