"""Tag parsing helpers for legacy prompt parsing."""

import re
from typing import Any

from core.helpers_core.emphasis_constants import (
    NAI_WEIGHT_RE as _NAI_WEIGHT_RE,
)
from core.helpers_core.emphasis_constants import (
    SD_WEIGHT_RE as _SD_WEIGHT_RE,
)

from .models import TemplateToken
from .utils import norm_space, split_namespace

_LBW_FRAGMENT_RE = re.compile(r"^[\d.]+>?$")
_LORA_FRAGMENT_RE = re.compile(r".*:[\d.]+>")


def _should_apply_sd_paren_weight(config: dict[str, Any], candidate: str) -> bool:
    mode = str(config.get("prompt_syntax", "auto") or "auto").strip().lower()
    if mode == "sd":
        return True
    if mode == "nai":
        return False
    return not ("::" in candidate or "||" in candidate)


def smart_split_by_comma(text: str) -> list[str]:
    result = []
    current = []
    paren_depth = 0
    brace_depth = 0
    angle_depth = 0
    for char in text:
        if char == "(":
            paren_depth += 1
            current.append(char)
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
            current.append(char)
        elif char == "{":
            brace_depth += 1
            current.append(char)
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
            current.append(char)
        elif char == "<":
            angle_depth += 1
            current.append(char)
        elif char == ">":
            angle_depth = max(0, angle_depth - 1)
            current.append(char)
        elif char == "," and paren_depth == 0 and brace_depth == 0 and angle_depth == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        result.append("".join(current))
    return [norm_space(x) for x in result if norm_space(x)]


def parse_candidate_tags(candidates: list[str], config: dict[str, Any]) -> list[tuple[str | None, str, float]]:
    tags: list[tuple[str | None, str, float]] = []

    for c in candidates:
        c = norm_space(c)
        if not c:
            continue
        if c.startswith("<lora:") or c.startswith("<lyco:") or c.startswith("<hypernet:"):
            continue
        # BUG-38: Reject colon-prefix remnants from NAI weight syntax
        if c.startswith(":"):
            continue
        if _LBW_FRAGMENT_RE.match(c):
            continue
        # BUG-53: LoRA weight fragment
        if _LORA_FRAGMENT_RE.match(c):
            continue
        if c.startswith("||") and c.endswith("||"):
            continue
        if config.get("brace_choice", False) and c.startswith("{") and c.endswith("}") and "|" in c:
            continue

        m = _NAI_WEIGHT_RE.search(c)
        if m:
            ns, t = split_namespace(norm_space(m.group(2)))
            tags.append((ns, t, float(m.group(1))))
            continue

        m = _SD_WEIGHT_RE.match(c)
        if m:
            ns, t = split_namespace(norm_space(m.group(1)))
            tags.append((ns, t, float(m.group(2))))
            continue

        if _should_apply_sd_paren_weight(config, c):
            paren_count = 0
            temp = c
            while temp.startswith("(") and temp.endswith(")"):
                paren_count += 1
                temp = temp[1:-1]
            if paren_count > 0:
                ns, t = split_namespace(norm_space(temp))
                tags.append((ns, t, 1.1**paren_count))
                continue

        ns, t = split_namespace(c)
        tags.append((ns, t, 1.0))

    return tags


def merge_template_choice_tags(tags: list[tuple[str | None, str, float]], template_tokens: list[TemplateToken]) -> None:
    for tok in template_tokens:
        if tok.token_type != "choice":
            continue
        for ch in tok.payload.get("choices", []):
            ns, t = split_namespace(ch)
            if t:
                tags.append((ns, t, 1.0))


def dedupe_normalize_tags(tags: list[tuple[str | None, str, float]], config: dict[str, Any]) -> list[tuple[str | None, str, float]]:
    normed: list[tuple[str | None, str, float]] = []
    seen: set[tuple[str | None, str]] = set()
    for ns, t, w in tags:
        ns2 = norm_space(ns) if ns else None
        t2 = norm_space(t)
        # BUG-50: Strip trailing/leading commas
        t2 = t2.strip(",").strip() if t2 else t2
        if ns2:
            ns2 = ns2.strip(",").strip()
        if config.get("lowercase_tags", True):
            ns2 = ns2.lower() if ns2 else None
            t2 = t2.lower()
        if not t2 or t2 == ":":
            continue
        # BUG-41: Strip duplicated namespace prefix from tag
        if ns2 and t2.startswith(ns2 + ":"):
            t2 = t2[len(ns2) + 1:].strip()
            if not t2:
                continue
        # BUG-39: Skip excessively long tags (parse artifacts)
        if len(t2) > 80:
            continue
        # BUG-51: Skip excessively long namespaces
        if ns2 and len(ns2) > 50:
            ns2 = None
        # BUG-52: Skip ADetailer parameter namespaces
        if ns2 and ns2.startswith("adetailer"):
            continue
        # BUG-53: Skip LoRA fragment namespaces
        if ns2 and "<lora" in ns2:
            continue
        # BUG-54: Round weight
        w = round(float(w), 4)
        key = (ns2, t2)
        if key in seen:
            continue
        seen.add(key)
        normed.append((ns2, t2, w))
    return normed
