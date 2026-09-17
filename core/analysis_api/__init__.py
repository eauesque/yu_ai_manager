"""Analysis API service exports."""

from core.analysis_api.batch_ops_dispatch import analyze_prompt_trends, start_batch_analysis
from core.analysis_api.config_ops import get_analysis_config, get_available_engines, save_analysis_config
from core.analysis_api.single_ops import analyze_one_file, get_analysis_result
from core.analysis_api.stats_ops import get_analysis_stats
from core.analysis_api.trend_history_ops import (
    delete_trend_history,
    get_trend_history,
)

__all__ = [
    "get_analysis_config",
    "get_available_engines",
    "save_analysis_config",
    "analyze_one_file",
    "get_analysis_result",
    "start_batch_analysis",
    "analyze_prompt_trends",
    "get_analysis_stats",
    "get_trend_history",
    "delete_trend_history",
]
