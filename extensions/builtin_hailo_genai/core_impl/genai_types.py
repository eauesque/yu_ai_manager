"""Type definitions for Hailo GenAI models."""

from dataclasses import dataclass
from enum import Enum


class GenAIModelType(Enum):
    """Supported GenAI model categories."""
    LLM = "llm"
    VLM = "vlm"
    SPEECH2TEXT = "s2t"


@dataclass(frozen=True)
class GenAIModelInfo:
    """Metadata for a downloadable GenAI HEF model."""
    name: str
    type: GenAIModelType
    hef_filename: str
    description: str
    url: str
