"""Candidate parsing helpers for prompt-to-tag conversion."""

import re
from typing import Any

from core.helpers_core.emphasis_constants import W_NUM
from core.helpers_core.helpers_text_path import norm_space, split_namespace
from core.parsers.prompt_defs import NAI_WEIGHT_RE, SD_WEIGHT_RE

# ---------------------------------------------------------------------------
# NAI meta_source detection
# ---------------------------------------------------------------------------

NAI_META_SOURCES: frozenset[str] = frozenset({
    "novelai_v4_png", "novelai_v4_webp", "novelai_v4",
    "novelai_png", "novelai_webp", "nai_webp",
})


def is_nai_meta_source(meta_source: str | None) -> bool:
    """Return True if *meta_source* indicates a NovelAI image."""
    return bool(meta_source and meta_source in NAI_META_SOURCES)


def effective_config(config: dict[str, Any], meta_source: str | None) -> dict[str, Any]:
    """Return *config* with ``prompt_syntax`` inferred from *meta_source*.

    If the caller already set an explicit ``prompt_syntax`` (anything other
    than ``None`` / ``""`` / ``"auto"``), that value is preserved.
    """
    if config.get("prompt_syntax") not in (None, "", "auto"):
        return config  # user explicitly chose a syntax — keep it
    if is_nai_meta_source(meta_source):
        cfg = dict(config)
        cfg["prompt_syntax"] = "nai"
        return cfg
    return config

_LBW_FRAGMENT_RE = re.compile(r"^[\d.]+>?$")

# BUG-53: LoRA weight fragments — "name:0.7>" or "name:1:1:lbw=...>"
_LORA_FRAGMENT_RE = re.compile(r".*:[\d.]+>")

# BUG-39: Tags longer than this are almost certainly parse artifacts
MAX_TAG_LENGTH = 80

# BUG-51: Namespace length limit
MAX_NAMESPACE_LENGTH = 50

# BUG-59: A1111 parameter keys that should never be namespaces
BLOCKED_NAMESPACES: frozenset[str] = frozenset({
    "model", "model hash", "sampler", "seed", "steps", "cfg scale",
    "clip skip", "size", "version", "vae", "vae hash",
    "denoising strength", "hires upscale", "hires steps",
    "hires upscaler", "rng", "schedule type", "token merging ratio",
})


def _should_apply_sd_paren_weight(prompt_syntax: str, candidate: str) -> bool:
    mode = (prompt_syntax or "auto").strip().lower()
    if mode == "sd":
        return True
    if mode == "nai":
        return False
    # auto: keep backward-compatible SD behavior unless explicit NAI markers are present.
    return not ("::" in candidate or "||" in candidate)


def parse_candidate(c: str, brace_choice: bool, prompt_syntax: str = "auto") -> tuple[str | None, str, float] | None:
    c = norm_space(c)
    if not c:
        return None
    if c.startswith("<lora:") or c.startswith("<lyco:") or c.startswith("<hypernet:"):
        return None
    # BUG-38: Reject colon-prefix remnants from NAI weight syntax
    if c.startswith(":"):
        return None
    if _LBW_FRAGMENT_RE.match(c):
        return None
    # BUG-53: LoRA weight fragment  e.g. "name:0.7>" or "name:1:lbw=x>"
    if _LORA_FRAGMENT_RE.match(c):
        return None
    if c.startswith("||") and c.endswith("||"):
        return None
    if brace_choice and c.startswith("{") and c.endswith("}") and "|" in c:
        return None

    m = NAI_WEIGHT_RE.search(c)
    if m:
        w = float(m.group(1))
        content = norm_space(m.group(2))
        ns, t = split_namespace(content)
        return ns, t, w

    m = SD_WEIGHT_RE.match(c)
    if m:
        content = norm_space(m.group(1))
        w = float(m.group(2))
        ns, t = split_namespace(content)
        return ns, t, w

    if _should_apply_sd_paren_weight(prompt_syntax, c):
        paren_count = 0
        temp = c
        while temp.startswith("(") and temp.endswith(")"):
            paren_count += 1
            temp = temp[1:-1]
        if paren_count > 0:
            weight = 1.1 ** paren_count
            content = norm_space(temp)
            ns, t = split_namespace(content)
            return ns, t, weight

    # NAI brace emphasis: {text}, {{text}}, etc.
    # {text} without | is never valid SD — safe in all prompt_syntax modes.
    brace_count = 0
    temp = c
    while temp.startswith("{") and temp.endswith("}") and "|" not in temp:
        brace_count += 1
        temp = temp[1:-1]
    if brace_count > 0:
        weight = 1.05 ** brace_count
        content = norm_space(temp)
        if content:
            ns, t = split_namespace(content)
            return ns, t, weight

    m_broken = re.match(rf"^(.+?):({W_NUM})\)$", c)
    if m_broken:
        content = norm_space(m_broken.group(1))
        w = float(m_broken.group(2))
        ns, t = split_namespace(content)
        if t and not re.match(r"^[\d.]+$", t):
            return ns, t, w

    cleaned = c
    cleaned = re.sub(r":[\d.]+\)", "", cleaned)
    cleaned = re.sub(r"(?<!\w)(?<!\\)\((?!\w)", "", cleaned)
    cleaned = re.sub(r"(?<!\w)(?<!\\)\)|(?<!\\)\)(?!\w)", "", cleaned)
    cleaned = re.sub(r"^\(+|(?<!\\)\)+$", "", cleaned)
    cleaned = re.sub(r"(?<!\w)\{(?!\w)", "", cleaned)
    cleaned = re.sub(r"(?<!\w)\}|\}(?!\w)", "", cleaned)
    cleaned = re.sub(r"^\{+|\}+$", "", cleaned)
    cleaned = norm_space(cleaned)
    if not cleaned:
        return None

    ns, t = split_namespace(cleaned)
    # BUG-67: Skip tags with no word characters (symbol-only garbage)
    if not t or not re.search(r"\w", t):
        return None
    return ns, t, 1.0


def normalize_tags(tags, lowercase_tags: bool):
    normed: list[tuple[str | None, str, float]] = []
    seen = set()

    for ns, t, w in tags:
        ns2 = norm_space(ns) if ns else None
        t2 = norm_space(t)
        # BUG-50: Strip trailing/leading commas
        t2 = t2.strip(",").strip() if t2 else t2
        if ns2:
            ns2 = ns2.strip(",").strip()
        if lowercase_tags:
            ns2 = ns2.lower() if ns2 else None
            t2 = t2.lower()
        if not t2 or t2 == ":":
            continue
        # BUG-67: Skip tags with no word characters (symbol-only garbage)
        if not re.search(r"\w", t2):
            continue
        # BUG-67: Skip colon-prefix weight remnants (e.g. ":1.3")
        if re.match(r"^:[\d.]+$", t2):
            continue
        # BUG-41: Strip duplicated namespace prefix from tag
        if ns2 and t2.startswith(ns2 + ":"):
            t2 = t2[len(ns2) + 1:].strip()
            if not t2:
                continue
        # BUG-39: Skip excessively long tags (parse artifacts)
        if len(t2) > MAX_TAG_LENGTH:
            continue
        # BUG-51: Skip excessively long namespaces (parse artifacts)
        if ns2 and len(ns2) > MAX_NAMESPACE_LENGTH:
            ns2 = None
        # BUG-52: Skip ADetailer parameter namespaces
        if ns2 and ns2.startswith("adetailer"):
            continue
        # BUG-53: Skip LoRA fragment namespaces
        if ns2 and "<lora" in ns2:
            continue
        # BUG-59: Block A1111 parameter keys as namespaces
        if ns2 and ns2 in BLOCKED_NAMESPACES:
            ns2 = None
        # BUG-54: Round weight to avoid float precision artifacts
        w = round(float(w), 4)
        key = (ns2, t2)
        if key in seen:
            continue
        seen.add(key)
        normed.append((ns2, t2, w))

    return normed
