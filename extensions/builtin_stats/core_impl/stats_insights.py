"""Stats insights compatibility facade."""

from .stats_insights_personality import analyze_personality
from .stats_insights_timeline import detect_resolution_changes, detect_story_events

__all__ = [
    "analyze_personality",
    "detect_resolution_changes",
    "detect_story_events",
]
