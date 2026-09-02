from .engines_claude import ClaudeVisionEngine
from .engines_ollama import OllamaVisionEngine
from .engines_openai import OpenAIVisionEngine
from .types import AnalysisEngine


def get_engine(engine_type: str, **kwargs) -> AnalysisEngine:
    if engine_type == "claude_api":
        return ClaudeVisionEngine(
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("model", "claude-sonnet-4-6-20250514"),
        )
    if engine_type == "openai":
        return OpenAIVisionEngine(
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("model", "gpt-4o-mini"),
        )
    if engine_type == "openai_compat":
        return OpenAIVisionEngine(
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("model", ""),
            base_url=kwargs.get("base_url", ""),
        )
    if engine_type == "ollama":
        return OllamaVisionEngine(
            base_url=kwargs.get("base_url", "http://localhost:11434"),
            model=kwargs.get("model", "llava:latest"),
        )
    if engine_type == "hailo_vlm":
        from .engines_hailo_vlm import HailoVLMEngine
        return HailoVLMEngine(model_name=kwargs.get("model_name", "qwen2-vl-2b-instruct"))
    raise ValueError(f"Unknown engine type: {engine_type}")
