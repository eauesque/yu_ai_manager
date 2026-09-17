"""Compatibility facade for stats API data builders.

Internal code should prefer ``core.stats_api.*`` concrete modules when a
stable import path exists. This file remains for older import paths.
"""

from core.stats_api import (
    build_basic_stats,
    build_hourly_stats,
    build_model_stats,
    build_resolution_stats,
    build_story_stats,
    build_timeline_stats,
)

__all__ = [
    "build_basic_stats",
    "build_timeline_stats",
    "build_hourly_stats",
    "build_model_stats",
    "build_resolution_stats",
    "build_story_stats",
]
