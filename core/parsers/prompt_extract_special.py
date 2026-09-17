"""LoRA / Embedding / Hypernetwork structured extraction utility.

Extracts special tokens (<lora:...>, <embedding:...>, etc.) from prompt strings
and returns them as structured data. Shared module.
"""

import contextlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# LoRA
# ---------------------------------------------------------------------------
_LORA_RE = re.compile(r"<lora:([^:>]+):([^>]+)>", re.IGNORECASE)


def extract_loras(prompt: str) -> list[dict[str, Any]]:
    """Extract <lora:name:weight>.

    Also supports extended syntax (LoRA Block Weight, etc.):
    ``<lora:name:1:1:lbw=0,0,0,1,1,1>``
    """
    loras: list[dict[str, Any]] = []
    for m in _LORA_RE.finditer(prompt):
        name = m.group(1).strip()
        params = m.group(2).strip()
        wm = re.match(r"^(-?\d*\.?\d+)", params)
        weight = float(wm.group(1)) if wm else 1.0
        entry: dict[str, Any] = {"name": name, "weight": weight}
        rest = params[wm.end():] if wm else params
        if rest.lstrip(":").strip():
            entry["extra"] = rest.lstrip(":").strip()
        loras.append(entry)
    return loras


# ---------------------------------------------------------------------------
# Embedding / Hypernetwork
# ---------------------------------------------------------------------------
# <embedding:name> | <embedding:name:weight>
_EMBED_ANGLE_RE = re.compile(
    r"<embedding:([^:>]+)(?::([^>]*))?>", re.IGNORECASE
)
# <hypernet:name> | <hypernet:name:weight>
_HYPERNET_RE = re.compile(
    r"<hypernet:([^:>]+)(?::([^>]*))?>", re.IGNORECASE
)
# (embedding:name) | (embedding:name:weight)
_EMBED_PAREN_RE = re.compile(
    r"\(embedding:([^:)]+)(?::([^)]*))?\)", re.IGNORECASE
)
# bare embedding:name -- exclude overlaps with angle/paren matches in post-processing
_EMBED_BARE_RE = re.compile(
    r"(?<![<(])embedding:([A-Za-z0-9_\-.]+)", re.IGNORECASE
)


def extract_embeddings(prompt: str) -> list[dict[str, Any]]:
    """Extract TI Embedding / Hypernetwork references.

    Supported formats:
    - ``<embedding:name>``  ``<embedding:name:weight>``
    - ``<hypernet:name>``  ``<hypernet:name:weight>``
    - ``(embedding:name)``  ``(embedding:name:weight)``
    - ``embedding:name``  (bare format)

    Returns:
        [{"name": "...", "weight": 1.0, "type": "embedding"|"hypernet"}, ...]
    """
    results: list[dict[str, Any]] = []
    seen_spans: list[tuple] = []

    def _add(name: str, weight_str: str | None, kind: str, span: tuple):
        name = name.strip()
        if not name:
            return
        w = 1.0
        if weight_str:
            weight_str = weight_str.strip()
            with contextlib.suppress(ValueError):
                w = float(weight_str)
        seen_spans.append(span)
        results.append({"name": name, "weight": w, "type": kind})

    for m in _EMBED_ANGLE_RE.finditer(prompt):
        _add(m.group(1), m.group(2), "embedding", m.span())

    for m in _HYPERNET_RE.finditer(prompt):
        _add(m.group(1), m.group(2), "hypernet", m.span())

    for m in _EMBED_PAREN_RE.finditer(prompt):
        _add(m.group(1), m.group(2), "embedding", m.span())

    # Bare form: exclude matches overlapping with already matched spans
    for m in _EMBED_BARE_RE.finditer(prompt):
        s, e = m.span()
        if any(ss <= s and e <= se for ss, se in seen_spans):
            continue
        _add(m.group(1), None, "embedding", (s, e))

    return results
