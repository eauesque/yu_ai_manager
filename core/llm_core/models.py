"""Data models and exceptions for the unified LLM client."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatMessage:
    """Single message in OpenAI chat format."""
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolCall:
    """Single tool call from LLM response."""
    id: str
    name: str
    arguments: str  # JSON string

    def parsed_arguments(self) -> dict:
        import json
        import logging
        try:
            return json.loads(self.arguments)
        except json.JSONDecodeError:
            logging.getLogger(__name__).warning(
                "ToolCall %s: malformed JSON arguments: %r", self.id, self.arguments
            )
            return {}


@dataclass
class ChatResponse:
    """Response from /v1/chat/completions."""
    content: str
    model: str = ""
    usage: dict[str, int] | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass
class StreamChunk:
    """Single chunk from streaming response."""
    delta: str = ""
    finish_reason: str | None = None


class LLMError(Exception):
    """Base exception for LLM client errors."""
    def __init__(self, message: str = ""):
        self.message = message
        super().__init__(message)


class LLMConnectionError(LLMError):
    """Network unreachable, DNS failure, timeout."""
    pass


class LLMResponseError(LLMError):
    """HTTP 4xx/5xx or malformed response."""
    def __init__(self, status_code: int = 0, message: str = ""):
        self.status_code = status_code
        super().__init__(message)
