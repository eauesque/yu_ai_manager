"""Thread-safe container for inference engine references.

Replaces the global mutable state pattern in deploy/hailo_tagger_server_state.py
with a proper class instance owned by CoworkManager.
"""

from __future__ import annotations

import threading
from typing import Any

YOLO_INIT_COOLDOWN: float = 60.0


class InferenceState:
    """Holds references to all inference engines with thread-safe access."""

    def __init__(self) -> None:
        # Tagger engine (no lock — single-writer at init)
        self._tagger_engine: Any = None
        self._tagger_model_name: str = ""
        self._general_threshold: float = 0.35
        self._character_threshold: float = 0.85

        # CLIP encoder
        self._clip_encoder: Any = None
        self._clip_backend: str = ""
        self._clip_lock = threading.Lock()

        # YOLO engine
        self._yolo_engine: Any = None
        self._yolo_input_size: int = 640
        self._yolo_init_failed: float = 0.0
        self._yolo_lock = threading.Lock()

        # Whisper backend
        self._whisper_backend: Any = None
        self._whisper_lock = threading.Lock()

        # Hailo vdevice
        self._hailo_vdevice: Any = None
        self._hailo_active_model: str = ""
        self._hailo_lock = threading.Lock()

        # LLM client (OpenAI-compat / Ollama / etc.)
        self._llm_client: Any = None
        self._llm_category: str = ""
        self._llm_lock = threading.Lock()

    # -- Tagger engine --

    def get_tagger_engine(self) -> Any:
        return self._tagger_engine

    def set_tagger_engine(
        self,
        engine: Any,
        model_name: str = "",
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
    ) -> None:
        self._tagger_engine = engine
        self._tagger_model_name = model_name
        self._general_threshold = general_threshold
        self._character_threshold = character_threshold

    def get_tagger_model_name(self) -> str:
        return self._tagger_model_name

    def get_general_threshold(self) -> float:
        return self._general_threshold

    def set_general_threshold(self, value: float) -> None:
        self._general_threshold = value

    def get_character_threshold(self) -> float:
        return self._character_threshold

    def set_character_threshold(self, value: float) -> None:
        self._character_threshold = value

    # -- CLIP encoder --

    def get_clip_encoder(self) -> Any:
        return self._clip_encoder

    def get_clip_backend(self) -> str:
        return self._clip_backend

    def set_clip_encoder(self, encoder: Any, backend: str = "") -> None:
        # No lock here — caller (get_clip_encoder) already holds _clip_lock
        self._clip_encoder = encoder
        self._clip_backend = backend

    # -- YOLO engine --

    def get_yolo_engine(self) -> Any:
        return self._yolo_engine

    def get_yolo_input_size(self) -> int:
        return self._yolo_input_size

    def get_yolo_init_failed(self) -> float:
        return self._yolo_init_failed

    def set_yolo_engine(
        self, engine: Any, input_size: int = 640
    ) -> None:
        # No lock here — caller (get_yolo_engine) already holds _yolo_lock
        self._yolo_engine = engine
        self._yolo_input_size = input_size
        self._yolo_init_failed = 0.0

    def set_yolo_init_failed(self, timestamp: float) -> None:
        # No lock here — caller already holds _yolo_lock
        self._yolo_init_failed = timestamp

    # -- Whisper backend --

    def get_whisper_backend(self) -> Any:
        return self._whisper_backend

    def set_whisper_backend(self, backend: Any) -> None:
        # No lock here — caller already holds _whisper_lock
        self._whisper_backend = backend

    # -- Hailo vdevice --

    def get_hailo_vdevice(self) -> Any:
        return self._hailo_vdevice

    def get_hailo_active_model(self) -> str:
        return self._hailo_active_model

    def set_hailo_vdevice(self, vdevice: Any, active_model: str = "") -> None:
        self._hailo_vdevice = vdevice
        self._hailo_active_model = active_model

    # -- LLM client --

    def get_llm_client(self) -> Any:
        with self._llm_lock:
            return self._llm_client

    def get_llm_category(self) -> str:
        with self._llm_lock:
            return self._llm_category

    def set_llm_client(self, client: Any, category: str = "general") -> None:
        with self._llm_lock:
            self._llm_client = client
            self._llm_category = category

    # -- Introspection --

    def get_inference_types(self) -> list[str]:
        """Return list of available inference type names."""
        types: list[str] = []
        if self._tagger_engine is not None:
            types.append("tagger")
        if self._clip_encoder is not None:
            types.append("clip")
        if self._yolo_engine is not None:
            types.append("yolo")
        if self._whisper_backend is not None:
            types.append("whisper")
        if self._hailo_vdevice is not None:
            types.append("hailo")
        if self._llm_client is not None:
            types.append("llm")
        return types
