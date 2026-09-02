import dataclasses
from typing import Any


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


@dataclasses.dataclass
class A1111Parsed:
    positive: str
    negative: str
    params: dict[str, str]
