import re

from core.helpers_core.emphasis_constants import W_NUM, W_SNUM


def convert_nai_to_sd(prompt: str) -> str:
    """NovelAI -> SD (A1111) format."""
    result = prompt

    def replace_weight(match):
        weight = match.group(1)
        content = match.group(2)
        return f"({content}:{weight})"

    result = re.sub(rf'({W_SNUM})::((?:[^:]|:[^:])+?)::', replace_weight, result)
    result = re.sub(r'\|\|([^|]+(?:\|[^|]+)*)\|\|', lambda m: f"{{{m.group(1)}}}", result)
    return result


def convert_sd_to_nai(prompt: str) -> str:
    """SD (A1111) -> NovelAI format."""
    result = prompt
    result = re.sub(r'<lora:[^>]+>', '', result, flags=re.IGNORECASE)
    result = re.sub(r'<(?:embedding|hypernet):[^>]+>', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\(embedding:[^\)]+\)', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\bembedding:[^\s,]+', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\{([^{}]+(?:\|[^{}]+)*)\}', lambda m: f"||{m.group(1)}||", result)
    result = re.sub(rf'\(([^():]+):({W_NUM})\)', lambda m: f"{m.group(2)}::{m.group(1)}::", result)
    result = re.sub(r'\s*,\s*,+', ',', result)
    result = re.sub(r'^\s*,+\s*|\s*,+\s*$', '', result)
    result = re.sub(r'\s{2,}', ' ', result)
    return result.strip()


def expand_dynamic_prompt(prompt: str, seed: int | None = None,
                          wildcards: dict | None = None) -> str:
    """Expand ||A|B||, {A|B|C}, and __wildcard__ style dynamic prompts."""
    import random

    if seed is not None:
        random.seed(seed)
    result = prompt

    # Resolve __wildcard__ references first
    if wildcards:
        def replace_wildcard(match):
            name = match.group(1)
            entries = wildcards.get(name)
            if entries and isinstance(entries, list) and len(entries) > 0:
                return random.choice(entries)
            return match.group(0)  # leave unresolved

        result = re.sub(r'__([a-zA-Z0-9_\-/]+)__', replace_wildcard, result)

    def replace_choice(match):
        body = match.group(1)
        choices = [c.strip() for c in body.split('|') if c.strip()]
        return random.choice(choices) if choices else ''

    result = re.sub(r'\|\|([^|]+(?:\|[^|]+)*)\|\|', replace_choice, result)

    # Pick-N / pick-range / weighted / simple choice — handle nested braces
    _PICK_RE = re.compile(r'^(\d+)(?:-(\d+))?\$\$(?:([^$]*)\$\$)?(.*)', re.S)

    def _find_matching_brace(text: str, start: int) -> int:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _split_top_level(inner: str) -> list:
        parts = []
        depth = 0
        cur = []
        for ch in inner:
            if ch == '{':
                depth += 1
                cur.append(ch)
            elif ch == '}':
                depth -= 1
                cur.append(ch)
            elif ch == '|' and depth == 0:
                parts.append(''.join(cur))
                cur = []
            else:
                cur.append(ch)
        parts.append(''.join(cur))
        return parts

    def _expand_braces(text: str) -> str:
        out = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                end = _find_matching_brace(text, i)
                if end == -1:
                    out.append(text[i])
                    i += 1
                    continue
                inner = text[i + 1:end]
                out.append(_resolve_brace(inner))
                i = end + 1
            else:
                out.append(text[i])
                i += 1
        return ''.join(out)

    def _resolve_brace(inner: str) -> str:
        # Check pick-N / pick-range prefix
        pm = _PICK_RE.match(inner)
        if pm:
            pick_min = int(pm.group(1))
            pick_max = int(pm.group(2)) if pm.group(2) else pick_min
            separator = pm.group(3) if pm.group(3) is not None else ', '
            rest = pm.group(4)
            choices = [c.strip() for c in _split_top_level(rest) if c.strip()]
            if not choices:
                return ''
            n = random.randint(min(pick_min, len(choices)),
                               min(pick_max, len(choices)))
            picked = random.sample(choices, n)
            return separator.join(_expand_braces(p) for p in picked)

        parts = _split_top_level(inner)
        if len(parts) < 2:
            # Not a choice — but recurse into inner for nested braces
            return '{' + _expand_braces(inner) + '}'

        # Weighted: {3::red|1::blue}
        # Disambiguate from NAI emphasis (2::tag::) embedded in a choice:
        # NAI emphasis closes with `::`, DP weighted prefix does not.
        # If the suffix contains `::`, treat the choice as plain text.
        weight_re = re.compile(rf'^({W_NUM})::(.*)', re.S)
        weighted = []
        for p in parts:
            stripped = p.strip()
            wm = weight_re.match(stripped)
            if wm and '::' not in wm.group(2):
                weighted.append((wm.group(2).strip(), float(wm.group(1))))
            else:
                weighted.append((stripped, 1.0))

        total_w = sum(w for _, w in weighted)
        if total_w <= 0:
            return ''
        r = random.random() * total_w
        cumul = 0.0
        chosen = weighted[-1][0]
        for text, w in weighted:
            cumul += w
            if r <= cumul:
                chosen = text
                break

        return _expand_braces(chosen)

    result = _expand_braces(result)
    return result
