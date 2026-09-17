"""Compatibility facade for legacy ``core.analysis`` imports.

Internal code should prefer concrete implementation modules where a stable
import path exists. This package remains as a compatibility bridge for older
callers.
"""

from importlib import import_module

_impl = import_module("extensions.builtin_analysis.core_impl")

AnalysisEngine = _impl.AnalysisEngine
AnalysisResult = _impl.AnalysisResult
ClaudeVisionEngine = _impl.ClaudeVisionEngine
HailoVLMEngine = _impl.HailoVLMEngine
OllamaVisionEngine = _impl.OllamaVisionEngine
OpenAIVisionEngine = _impl.OpenAIVisionEngine
get_engine = _impl.get_engine
ensure_analysis_table = _impl.ensure_analysis_table
save_analysis = _impl.save_analysis
save_analysis_batch = _impl.save_analysis_batch
get_analysis = _impl.get_analysis
get_all_analyses = _impl.get_all_analyses

__all__ = [
    "AnalysisEngine",
    "AnalysisResult",
    "ClaudeVisionEngine",
    "HailoVLMEngine",
    "OllamaVisionEngine",
    "OpenAIVisionEngine",
    "get_engine",
    "ensure_analysis_table",
    "save_analysis",
    "save_analysis_batch",
    "get_analysis",
    "get_all_analyses",
]
