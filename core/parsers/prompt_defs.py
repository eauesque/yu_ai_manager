"""Shared types and regex definitions for prompt parser."""

import dataclasses
import re
from typing import Any

from core.helpers_core.emphasis_constants import (
    SD_WEIGHT_RE,  # noqa: F401 -- re-export
    W_SNUM,
)


@dataclasses.dataclass
class TemplateToken:
    token_type: str
    payload: dict[str, Any]
    position: int


@dataclasses.dataclass
class ParsedPrompt:
    raw_prompt: str
    tags: list[tuple[str | None, str, float]]
    template_tokens: list[TemplateToken]


NAI_WEIGHT_RE = re.compile(rf"({W_SNUM})::((?:[^:]|:[^:])+?)::")
NAI_CHOICE_RE = re.compile(r"\|\|(?P<body>[^|].*?)\|\|")
BRACE_CHOICE_RE = re.compile(r"\{(?P<body>[^{}]+)\}")
# SD_WEIGHT_RE is imported from emphasis_constants (re-exported above)
