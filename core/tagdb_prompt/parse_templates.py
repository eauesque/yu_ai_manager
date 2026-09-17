"""Template extraction helpers for legacy prompt parsing."""

import re
from typing import Any

from .models import TemplateToken
from .utils import norm_space

_NAI_CHOICE_RE = re.compile(r"\|\|(?P<body>[^|].*?)\|\|")
_BRACE_CHOICE_RE = re.compile(r"\{(?P<body>[^{}]+)\}")


def extract_template_choices(text: str, config: dict[str, Any], template_tokens: list[TemplateToken]) -> str:
    def _extract_nai_choices(t: str) -> str:
        out: list[str] = []
        pos = 0
        for m in _NAI_CHOICE_RE.finditer(t):
            if m.start() > pos:
                out.append(t[pos : m.start()])
            body = m.group(1)
            choices = [norm_space(x) for x in body.split("|") if norm_space(x)]
            template_tokens.append(TemplateToken("choice", {"syntax": "|| ||", "choices": choices}, position=len(template_tokens)))
            out.append(m.group(0) if config.get("preserve_templates", True) else (choices[0] if choices else ""))
            pos = m.end()
        out.append(t[pos:])
        return "".join(out)

    out_text = _extract_nai_choices(text)

    if config.get("brace_choice", False):
        out: list[str] = []
        pos = 0
        for m in _BRACE_CHOICE_RE.finditer(out_text):
            body = m.group(1)
            if "|" not in body:
                continue
            if m.start() > pos:
                out.append(out_text[pos : m.start()])
            choices = [norm_space(x) for x in body.split("|") if norm_space(x)]
            template_tokens.append(TemplateToken("choice", {"syntax": "{ }", "choices": choices}, position=len(template_tokens)))
            out.append(m.group(0) if config.get("preserve_templates", True) else (choices[0] if choices else ""))
            pos = m.end()
        out.append(out_text[pos:])
        out_text = "".join(out)

    return out_text
