"""Abstract base class for CLIP image encoders.

All CLIP image encoder backends (Hailo, ONNX, etc.) must implement
this interface so that the indexer and factory can use them
interchangeably.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class ClipImageEncoder(abc.ABC):
    """Abstract CLIP image encoder."""

    @abc.abstractmethod
    def encode(self, image: np.ndarray) -> np.ndarray:
        """Encode a single preprocessed image to a float32 vector.

        Args:
            image: Preprocessed image array (format depends on backend).

        Returns:
            (dim,) float32 L2-normalized vector.
        """

    def encode_batch(self, images: np.ndarray) -> np.ndarray:
        """Encode a batch of preprocessed images.

        Default implementation processes sequentially.
        Subclasses may override for true batch inference.

        Args:
            images: (N, ...) array of preprocessed images.

        Returns:
            (N, dim) float32 normalized vectors.
        """
        import numpy as np

        return np.stack([self.encode(img) for img in images])

    @abc.abstractmethod
    def close(self) -> None:
        """Release resources held by this encoder."""

    @property
    @abc.abstractmethod
    def output_dim(self) -> int:
        """Dimensionality of the output embedding (e.g. 512)."""

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend identifier (e.g. 'hailo-10h', 'onnx-CUDA')."""
