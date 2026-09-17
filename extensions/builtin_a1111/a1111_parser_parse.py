"""Parsing utilities for A1111 metadata extraction."""

import re
from pathlib import Path
from typing import Any


def extract_parameters_text(chunks: dict[str, str]) -> str | None:
    """Find Parameters text in metadata chunks."""
    for key in ("parameters", "Parameters", "PARAMETERS"):
        val = chunks.get(key)
        if isinstance(val, str) and val.strip():
            return val

    for key, val in chunks.items():
        if isinstance(key, str) and key.strip().lower() == "parameters":  # noqa: SIM102
            if isinstance(val, str) and val.strip():
                return val

    return None


def parse_a1111(params_text: str) -> tuple[str, str, dict[str, str]]:
    """Split A1111 Parameters text into positive/negative/params."""
    text = (params_text or "").strip()
    text = text.lstrip("\ufeff")
    if not text:
        return "", "", {}

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
            stripped = lines[i].strip()
            if stripped:
                neg_lines.append(stripped)
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
                k = k.strip()
                v = v.strip()
                if k:
                    params[k] = v

    return positive, negative, params


def extract_loras(prompt: str) -> list[dict[str, Any]]:
    """Extract LoRA tags from prompt text.

    Handles extended syntax like LoRA Block Weight:
    ``<lora:name:1:1:lbw=0,0,0,1,1,1>``
    """
    loras: list[dict[str, Any]] = []
    for m in re.finditer(r"<lora:([^:>]+):([^>]+)>", prompt):
        name = m.group(1).strip()
        params = m.group(2).strip()
        # Extract leading numeric weight from params
        wm = re.match(r"^(-?\d*\.?\d+)", params)
        weight = float(wm.group(1)) if wm else 1.0
        entry: dict[str, Any] = {"name": name, "weight": weight}
        # Preserve extra parameters (e.g. "1:lbw=0,0,0,1")
        rest = params[wm.end():] if wm else params
        if rest.lstrip(":").strip():
            entry["extra"] = rest.lstrip(":").strip()
        loras.append(entry)
    return loras


def detect_meta_source(filepath: str, chunks: dict[str, str]) -> str:
    """Determine metadata source label by file extension and chunks."""
    suffix = Path(filepath.split("!")[0] if "!" in filepath else filepath).suffix.lower()
    if "nai_json" in chunks:
        return "nai_webp"
    if suffix == ".webm":
        return "a1111_webm"
    if suffix == ".webp":
        return "a1111_webp"
    if suffix in (".jpg", ".jpeg"):
        return "a1111_jpg"
    if suffix == ".jxl":
        return "a1111_jxl"
    if suffix in (".avif",):
        return "a1111_avif"
    if suffix in (".heif", ".heic"):
        return "a1111_heif"
    return "a1111_png"


# re-export: expose embedding extraction from shared module
from core.parsers.prompt_extract_special import extract_embeddings  # noqa: F401
