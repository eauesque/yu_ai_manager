"""Compatibility facade for prompt parser exports.

External compatibility only. Repo-internal code should prefer
``prompt_parse`` and ``prompt_defs`` directly.
"""

from core.parsers.prompt_defs import ParsedPrompt, TemplateToken
from core.parsers.prompt_parse import parse_prompt_to_tags

__all__ = [
    "TemplateToken",
    "ParsedPrompt",
    "parse_prompt_to_tags",
]
