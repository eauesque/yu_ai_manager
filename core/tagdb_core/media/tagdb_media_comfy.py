"""ComfyUI metadata helpers for legacy media parsing."""

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
    pos: list[str] = []
    neg: list[str] = []

    if not isinstance(obj, dict):
        return pos, neg

    nodes = obj["nodes"] if isinstance(obj.get("nodes"), list) else list(obj.values())

    for n in nodes:
        if not isinstance(n, dict):
            continue
        cls = n.get("class_type") or n.get("type")
        if not isinstance(cls, str):
            cls = ""
        cls_l = cls.lower()

        inputs = n.get("inputs") if isinstance(n.get("inputs"), dict) else None

        if "cliptextencode" in cls_l and inputs is not None:
            t = inputs.get("text")
            if isinstance(t, str) and t.strip():
                pos.append(t.strip())

        # Audio sampler nodes (MMAudioSampler, AudioLDMSampler, ...) and other
        # non-CLIP nodes expose prompt / negative_prompt directly on inputs.
        if inputs is not None:
            for k in ("prompt", "positive_prompt"):
                v = inputs.get(k)
                if isinstance(v, str) and v.strip():
                    pos.append(v.strip())
                    break
            v = inputs.get("negative_prompt")
            if isinstance(v, str) and v.strip():
                neg.append(v.strip())

        meta = n.get("_meta")
        title = meta.get("title") if isinstance(meta, dict) else None
        if isinstance(title, str) and "negative" in title.lower() and inputs is not None:
            t = inputs.get("text")
            if isinstance(t, str) and t.strip():
                neg.append(t.strip())

    return pos, neg
