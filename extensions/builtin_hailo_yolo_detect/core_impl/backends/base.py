"""YOLO detection backend abstract base class."""

from abc import ABC, abstractmethod

import numpy as np


class YoloBackend(ABC):
    """Abstract base for YOLO detection backends."""

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
    def load_model(self, model_name: str, input_size: int = 640) -> None:
        """Load or switch to the given YOLO model.

        Args:
            model_name: Model identifier (e.g. "yolov8s").
            input_size: Input image dimension for the model.
        """

    @abstractmethod
    def detect(
        self,
        image: np.ndarray,
        scale_info: dict | None = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> list[dict]:
        """Run detection on an image.

        Args:
            image: BGR numpy array.
            scale_info: Optional scaling metadata for coordinate mapping.
            conf_threshold: Confidence threshold for filtering detections.
            iou_threshold: IoU threshold for NMS.

        Returns:
            List of detection dicts with keys like
            "label", "confidence", "bbox", etc.
        """

    @property
    @abstractmethod
    def input_size(self) -> int:
        """Return the model input dimension."""

    def close(self) -> None:
        """Release resources. Default is no-op."""
        return None

    @property
    def model_name(self) -> str:
        """Currently loaded model name."""
        return getattr(self, "_model_name", "")

    @staticmethod
    def supported_models() -> list[str]:
        """Return list of model names this backend supports.

        Subclasses should override to advertise available models.
        """
        return []

    def detect_batch(
        self,
        images: list[np.ndarray],
        scale_infos: list[dict | None],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> list[list[dict]]:
        """Run detection on a batch of images.

        Default implementation calls detect() in a loop.
        Backends with native batch support should override this.

        Returns:
            List of detection lists, one per image.
        """
        results = []
        for img, si in zip(images, scale_infos, strict=False):
            results.append(self.detect(img, si, conf_threshold, iou_threshold))
        return results

    def info(self) -> dict:
        """Return backend info dict for status API."""
        return {
            "name": self.name,
            "model_name": self.model_name,
            "input_size": self.input_size,
            "available": self.is_available(),
        }
