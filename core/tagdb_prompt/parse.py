from typing import Any

from core.parsers.prompt_preprocess import preprocess_prompt_text

from .models import ParsedPrompt, TemplateToken
from .parse_tags import dedupe_normalize_tags, merge_template_choice_tags, parse_candidate_tags, smart_split_by_comma
from .parse_templates import extract_template_choices


def parse_prompt_to_tags(raw: str, config: dict[str, Any]) -> ParsedPrompt:
    text = raw or ""
    template_tokens: list[TemplateToken] = []

    text = extract_template_choices(text, config, template_tokens)
    # BUG-33~44: Shared pre-processing pipeline
    text = preprocess_prompt_text(text)
    candidates = smart_split_by_comma(text)

    tags = parse_candidate_tags(candidates, config)
    merge_template_choice_tags(tags, template_tokens)
    normed = dedupe_normalize_tags(tags, config)

    return ParsedPrompt(raw_prompt=raw, tags=normed, template_tokens=template_tokens)
