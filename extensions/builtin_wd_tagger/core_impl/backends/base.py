"""Backend session abstraction.

A BackendSession wraps the concrete inference engine
(onnxruntime InferenceSession, torch nn.Module, etc.) and exposes
a uniform run() / get_input_name() interface to TaggerAdapters.

Spec § 3.1 / § 4.1.
"""
from __future__ import annotations

import abc

import numpy as np


class BackendSession(abc.ABC):
    """Abstract inference backend.

    Concrete subclasses: OnnxBackendSession (Phase 1a),
    PyTorchBackendSession (Phase 3), VlmBackendSession (Phase 3).
    """

    @abc.abstractmethod
    def get_input_name(self) -> str:
        """Return the model input tensor name (for ONNX) or 'input'."""

    @abc.abstractmethod
    def run(
        self,
        input_array: np.ndarray,
        output_key: str | None = None,
    ) -> np.ndarray:
        """Run inference and return one raw output tensor.

        Input shape: (N, ...) batch-first.
        Output shape: (N, num_tags) for tagger models.

        ``output_key`` names which output head to return for multi-head
        models. None keeps the historical behaviour of returning the first
        output, which is the only one WD exports.
        """

    @abc.abstractmethod
    def is_loaded(self) -> bool:
        """Whether the backend has loaded the model and is ready to run()."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release resources (GPU memory, file handles)."""
