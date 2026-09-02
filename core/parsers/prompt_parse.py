"""Prompt-to-tag parser implementation."""

from typing import Any

from core.helpers_core.helpers_text_path import split_namespace
from core.parsers.prompt_defs import ParsedPrompt, TemplateToken
from core.parsers.prompt_parse_candidates import normalize_tags, parse_candidate
from core.parsers.prompt_parse_templates import (
    extract_brace_choices,
    extract_nai_choices,
    strip_a1111_positive_only,
)
from core.parsers.prompt_preprocess import preprocess_prompt_text
from core.parsers.prompt_split import smart_split_by_comma


def parse_prompt_to_tags(raw: str, config: dict[str, Any]) -> ParsedPrompt:
    text = strip_a1111_positive_only(raw or "")
    template_tokens: list[TemplateToken] = []

    text = extract_nai_choices(text, config, template_tokens)
    if config.get("brace_choice", False):
        text = extract_brace_choices(text, config, template_tokens)

    # BUG-33~44: Shared pre-processing pipeline (BREAK, alternation,
    # bare colons, brace emphasis, angle blocks, adjacent weights)
    text = preprocess_prompt_text(text)

    tags = []
    prompt_syntax = str(config.get("prompt_syntax", "auto"))
    for c in smart_split_by_comma(text):
        parsed = parse_candidate(
            c,
            brace_choice=bool(config.get("brace_choice", False)),
            prompt_syntax=prompt_syntax,
        )
        if parsed:
            tags.append(parsed)

    for tok in template_tokens:
        if tok.token_type != "choice":
            continue
        for ch in tok.payload.get("choices", []):
            ns, t = split_namespace(ch)
            if t:
                tags.append((ns, t, 1.0))

    normed = normalize_tags(tags, lowercase_tags=bool(config.get("lowercase_tags", True)))
    return ParsedPrompt(raw_prompt=raw, tags=normed, template_tokens=template_tokens)
