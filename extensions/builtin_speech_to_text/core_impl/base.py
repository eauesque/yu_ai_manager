"""S2T backend abstract base class."""

from abc import ABC, abstractmethod

import numpy as np


class S2TBackend(ABC):
    """Abstract base for Speech-to-Text backends."""

    name: str = "unknown"

    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """Return True if this backend can be used on the current system."""

    @staticmethod
    @abstractmethod
    def priority() -> int:
        """Higher = preferred when multiple backends are available."""

    @abstractmethod
    def load_model(self, model_size: str) -> None:
        """Load or switch to the given Whisper model size."""

    @abstractmethod
    def transcribe(
        self,
        audio_data: np.ndarray,
        language: str = "en",
    ) -> list[dict]:
        """Transcribe audio and return segment list.

        Args:
            audio_data: PCM int16 or float32 mono 16 kHz.
            language: BCP-47 language code.

        Returns:
            List of {"text": str, "start": float, "end": float}.
        """

    @abstractmethod
    def close(self) -> None:
        """Release resources. Default is no-op."""

    @property
    def model_size(self) -> str:
        """Currently loaded model size."""
        return getattr(self, "_model_size", "")

    @staticmethod
    def cached_models() -> list:
        """Return list of locally cached model sizes.

        Each entry: {"size": str, "path": str, "size_bytes": int}.
        Subclasses should override to provide real detection.
        """
        return []

    def info(self) -> dict:
        """Return backend info dict for status API."""
        return {
            "name": self.name,
            "model_size": self.model_size,
            "available": self.is_available(),
        }
