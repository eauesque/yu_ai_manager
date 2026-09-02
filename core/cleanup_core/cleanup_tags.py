"""Compatibility facade for tag cleanup helpers.

External compatibility only. Repo-internal code should prefer
``cleanup_tag_merge`` and ``cleanup_tag_normalize`` directly.
"""

from .cleanup_tag_merge import cleanup_normalize_tags
from .cleanup_tag_normalize import normalize_tag_string

__all__ = [
    "normalize_tag_string",
    "cleanup_normalize_tags",
]
