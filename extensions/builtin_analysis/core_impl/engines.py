from .engines_claude import ClaudeVisionEngine
from .engines_factory import get_engine
from .engines_ollama import OllamaVisionEngine
from .engines_openai import OpenAIVisionEngine
from .types import AnalysisEngine, AnalysisResult

try:
    from .engines_hailo_vlm import HailoVLMEngine
except ImportError:
    HailoVLMEngine = None  # type: ignore[assignment,misc]

__all__ = [
    "AnalysisResult",
    "AnalysisEngine",
    "ClaudeVisionEngine",
    "HailoVLMEngine",
    "OllamaVisionEngine",
    "OpenAIVisionEngine",
    "get_engine",
]
