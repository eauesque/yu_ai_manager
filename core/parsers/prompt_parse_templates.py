"""Template extraction helpers for prompt parsing."""

from typing import Any

from core.helpers_core.helpers_text_path import norm_space
from core.parsers.prompt_defs import BRACE_CHOICE_RE, NAI_CHOICE_RE, TemplateToken


def strip_a1111_positive_only(text: str) -> str:
    if "\nNegative prompt:" in text or "\nSteps:" in text:
        lines = text.split("\n")
        positive_lines = []
        for line in lines:
            if line.startswith("Negative prompt:") or line.startswith("Steps:"):
                break
            positive_lines.append(line)
        return "\n".join(positive_lines).strip()
    return text


def extract_nai_choices(text: str, config: dict[str, Any], template_tokens: list[TemplateToken]) -> str:
    out: list[str] = []
    pos = 0
    for m in NAI_CHOICE_RE.finditer(text):
        if m.start() > pos:
            out.append(text[pos : m.start()])
        body = m.group(1)
        choices = [norm_space(x) for x in body.split("|") if norm_space(x)]
        template_tokens.append(TemplateToken("choice", {"syntax": "|| ||", "choices": choices}, position=len(template_tokens)))
        if config.get("preserve_templates", True):
            out.append(m.group(0))
        else:
            out.append(choices[0] if choices else "")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def extract_brace_choices(text: str, config: dict[str, Any], template_tokens: list[TemplateToken]) -> str:
    out: list[str] = []
    pos = 0
    for m in BRACE_CHOICE_RE.finditer(text):
        body = m.group(1)
        if "|" not in body:
            continue
        if m.start() > pos:
            out.append(text[pos : m.start()])
        choices = [norm_space(x) for x in body.split("|") if norm_space(x)]
        template_tokens.append(TemplateToken("choice", {"syntax": "{ }", "choices": choices}, position=len(template_tokens)))
        if config.get("preserve_templates", True):
            out.append(m.group(0))
        else:
            out.append(choices[0] if choices else "")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)
