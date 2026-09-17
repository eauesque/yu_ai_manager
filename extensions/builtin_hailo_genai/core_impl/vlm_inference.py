"""Hailo-10H VLM inference wrapper (singleton).

Wraps ``hailo_platform.genai.VLM`` with device_manager integration.
Supports image + text prompts for visual understanding.
"""

import logging
import threading
from collections.abc import Iterator
from typing import Optional

import numpy as np

from .model_download import get_hef_path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: Optional["HailoVLM"] = None

# Special token filter shared with LLM
from .llm_inference import _filter_token

# VLM expects 336x336 RGB uint8 images
VLM_INPUT_SIZE = 336


class HailoVLM:
    """Thin wrapper around ``hailo_platform.genai.VLM``."""

    def __init__(self, model_name: str):
        from hailo_platform.genai import VLM

        from core.hailo_device_core.device_manager import acquire_genai

        path = str(get_hef_path(model_name))
        self._vlm = acquire_genai(
            "vlm", path,
            lambda vd, p: VLM(vd, p),
        )
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def _build_vlm_prompt(self, text: str) -> list:
        """Build a structured chat prompt for VLM.

        Hailo VLM は ``[{"role": "user", "content": [{"type": "text", ...},
        {"type": "image"}]}]`` 形式を期待する。
        """
        return [{
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": text},
            ],
        }]

    def generate_stream(
        self,
        prompt: str,
        frames: list[np.ndarray],
        *,
        temperature: float = 0.7,
        max_generated_tokens: int = 512,
        seed: int | None = None,
    ) -> Iterator[str]:
        """Yield tokens with image frames.

        Note: VLM requires ``frames`` — image-free generation is not
        supported by the Hailo-10H VLM model.
        """
        # HailoRT 5.3.0+ rejects temperature=0.0 with HAILO_INVALID_ARGUMENT.
        temperature = max(temperature, 0.01)
        structured_prompt = self._build_vlm_prompt(prompt)
        kwargs = {
            "prompt": structured_prompt,
            "frames": frames,
            "temperature": temperature,
            "max_generated_tokens": max_generated_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        # Hailo VLM.generate() is used as a context manager
        with self._vlm.generate(**kwargs) as gen:
            for token in gen:
                filtered = _filter_token(token)
                if filtered is None:
                    continue
                yield filtered

    def generate_all(
        self,
        prompt: str,
        frames: list[np.ndarray],
        *,
        temperature: float = 0.7,
        max_generated_tokens: int = 512,
        seed: int | None = None,
    ) -> str:
        """Non-streaming generation with image frames.

        Note: VLM requires ``frames`` — image-free generation is not
        supported by the Hailo-10H VLM model.
        """
        temperature = max(temperature, 0.01)
        structured_prompt = self._build_vlm_prompt(prompt)
        kwargs = {
            "prompt": structured_prompt,
            "frames": frames,
            "temperature": temperature,
            "max_generated_tokens": max_generated_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        text = self._vlm.generate_all(**kwargs)
        from .llm_inference import _STOP_TOKENS
        for st in _STOP_TOKENS:
            text = text.replace(st, "")
        return text.strip()

    def get_context_info(self) -> dict:
        return {
            "usage": self._vlm.get_context_usage_size(),
            "capacity": self._vlm.max_context_capacity(),
        }

    def clear_context(self) -> None:
        self._vlm.clear_context()

    def close(self) -> None:
        from core.hailo_device_core.device_manager import release_device
        release_device("vlm")


def preprocess_image(image_bgr: np.ndarray) -> np.ndarray:
    """Convert a BGR image (OpenCV default) to RGB uint8, resized to 336x336."""
    import cv2

    if len(image_bgr.shape) == 3 and image_bgr.shape[2] == 3:
        image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    else:
        image = image_bgr
    image = cv2.resize(
        image, (VLM_INPUT_SIZE, VLM_INPUT_SIZE),
        interpolation=cv2.INTER_LINEAR,
    )
    return image.astype(np.uint8)


def get_vlm(model_name: str = "qwen2-vl-2b-instruct") -> HailoVLM:
    """Return the singleton HailoVLM, loading *model_name* if needed."""
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            return _instance
        if _instance is not None:
            _instance.close()
            _instance = None
        _instance = HailoVLM(model_name)
        return _instance


def close_vlm() -> None:
    """Release the singleton VLM."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
            _instance = None
