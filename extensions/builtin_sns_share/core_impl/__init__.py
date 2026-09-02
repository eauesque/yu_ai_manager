"""SNS Share core -- business logic layer for SNS sharing.

Manages the sns section of config.json, expands post templates,
generates X Intent URLs, and provides Bluesky posting.
"""

from .credential_store import load_sns_config, save_sns_config
from .post_builder import build_post_text, build_x_intent_url, count_graphemes

__all__ = [
    "load_sns_config",
    "save_sns_config",
    "build_post_text",
    "build_x_intent_url",
    "count_graphemes",
]
