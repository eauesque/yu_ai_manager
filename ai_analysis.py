"""
AI Analysis public facade.

routes/analysis.py 互換のため、公開APIはここで再エクスポートする。
"""

from core.analysis import (
    AnalysisEngine,
    AnalysisResult,
    ClaudeVisionEngine,
    HailoVLMEngine,
    OllamaVisionEngine,
    OpenAIVisionEngine,
    ensure_analysis_table,
    get_all_analyses,
    get_analysis,
    get_engine,
    save_analysis,
    save_analysis_batch,
)

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
