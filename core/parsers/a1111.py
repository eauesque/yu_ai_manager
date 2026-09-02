"""A1111 Parameters parser"""

import dataclasses
import re

from core.helpers_core.helpers_text_path import norm_space


@dataclasses.dataclass
class A1111Parsed:
    positive: str
    negative: str
    params: dict[str, str]



def parse_a1111_parameters(params_text: str) -> A1111Parsed:
    """Parse Automatic1111 parameters (supports both multi-line and single-line concatenated)."""
    text = (params_text or "").strip()
    text = text.lstrip(chr(65279))
    if not text:
        return A1111Parsed("", "", {})

    text = re.sub(r"^\s*Parameters?\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\.\s*(Negative prompt:)", r"\n\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\.\s*(Steps:)", r"\n\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(Negative prompt:)", r"\n\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(Steps:)", r"\n\1", text, flags=re.IGNORECASE)

    lines = text.splitlines()

    pos_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r"^Negative prompt:", line, flags=re.IGNORECASE) or line.startswith("Steps:"):
            break
        pos_lines.append(lines[i])
        i += 1
    positive = "\n".join(pos_lines).strip()

    neg_lines: list[str] = []
    if i < len(lines) and re.match(r"^Negative prompt:", lines[i].strip(), flags=re.IGNORECASE):
        first = re.sub(r"^Negative prompt:\s*", "", lines[i].strip(), flags=re.IGNORECASE)
        if first:
            neg_lines.append(first)
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("Steps:"):
            if norm_space(lines[i]):
                neg_lines.append(lines[i].strip())
            i += 1
    negative = "\n".join(neg_lines).strip()

    params: dict[str, str] = {}
    if i < len(lines):
        param_line = lines[i].strip()
        if param_line.startswith("Steps:"):
            parts = [p.strip() for p in param_line.split(",") if p.strip()]
            for part in parts:
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                k = norm_space(k)
                v = norm_space(v)
                if k:
                    params[k] = v

    return A1111Parsed(positive, negative, params)



def extract_a1111_parameters(chunks: dict[str, str]) -> str | None:
    """Return A1111 parameters text from PNG chunks (case-insensitive)."""
    if not chunks:
        return None

    for k in ("parameters", "Parameters", "PARAMETERS"):
        v = chunks.get(k)
        if isinstance(v, str) and v.strip():
            return v

    for k, v in chunks.items():
        if isinstance(k, str) and k.strip().lower() == "parameters" and isinstance(v, str) and v.strip():
            return v
    return None

