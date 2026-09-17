"""Dataclasses used across the LLM router."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelInfo:
    """A single model exposed by a backend."""

    id: str          # full physical name "ollama-mac/qwen2.5-coder:32b"
    backend: str     # alias only "ollama-mac"
    name: str        # raw backend-side name "qwen2.5-coder:32b"
    context_window: int | None = None
    size_b: float | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class BackendInfo:
    """A physical OpenAI-compatible backend host."""

    alias: str
    base_url: str
    type: str  # "ollama" | "hailo-ollama" | "openai-compat"
    api_key: str = ""
    status: str = "unknown"  # "ready" | "unreachable" | "unknown"
    models: list[ModelInfo] = field(default_factory=list)
    last_seen_at: str | None = None
    last_error: str | None = None
    slo_state: str | None = None  # "vision_idle" | "vision_active" | "unknown"
    auto_discover: bool = True
    respect_vision_load: bool = False
    disabled: bool = False
    source: str = "static"  # "static" | "mdns" | "llm_core"


@dataclass
class StreamState:
    """Mutable state held during a single streaming SSE translation."""

    message_started: bool = False
    current_block_index: int = 0
    in_text_block: bool = False
    in_tool_block: bool = False
    current_tool_id: str | None = None
    current_tool_name: str | None = None
    message_id: str | None = None
    model: str | None = None
