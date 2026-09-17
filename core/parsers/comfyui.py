"""ComfyUI workflow JSON parser"""

import json
from typing import Any


def extract_comfyui_json(chunks: dict[str, str]) -> tuple[str | None, dict[str, Any] | None]:
    for key in ("prompt", "workflow"):
        raw = chunks.get(key)
        if raw and raw.strip():
            raw = raw.strip()
            try:
                return raw, json.loads(raw)
            except Exception:
                return raw, None
    return None, None



def comfyui_find_clip_texts(obj: Any) -> tuple[list[str], list[str]]:
    """Best-effort: extract positive/negative texts from ComfyUI JSON."""
    pos: list[str] = []
    neg: list[str] = []

    if not isinstance(obj, dict):
        return pos, neg

    # Common: obj may have 'nodes' list or be dict of nodes keyed by id.
    nodes = obj["nodes"] if isinstance(obj.get("nodes"), list) else list(obj.values())

    for n in nodes:
        if not isinstance(n, dict):
            continue
        cls = n.get("class_type") or n.get("type")
        if not isinstance(cls, str):
            cls = ""
        cls_l = cls.lower()

        if "cliptextencode" in cls_l:
            inputs = n.get("inputs")
            if isinstance(inputs, dict):
                t = inputs.get("text")
                if isinstance(t, str) and t.strip():
                    pos.append(t.strip())

        # Heuristic negative: title contains 'negative'
        meta = n.get("_meta")
        title = meta.get("title") if isinstance(meta, dict) else None
        if isinstance(title, str) and "negative" in title.lower():
            inputs = n.get("inputs")
            if isinstance(inputs, dict):
                t = inputs.get("text")
                if isinstance(t, str) and t.strip():
                    neg.append(t.strip())

    return pos, neg


# -----------------------------
# SQLite schema
# -----------------------------


