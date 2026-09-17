"""Resolution extraction utilities for scanner I/O.

Extracts width/height from raw prompt text and metadata JSON
(A1111, NAI, ComfyUI formats).
"""

import json
import re

_RE_SIZE = re.compile(r"Size:\s*(\d+)\s*x\s*(\d+)")

# BUG-40: ComfyUI latent-image node classes that carry width/height
_COMFYUI_LATENT_CLASSES = frozenset({
    "EmptyLatentImage", "EmptySD3LatentImage",
})


def _extract_comfyui_resolution(obj: dict) -> tuple[int | None, int | None]:
    """Extract width/height from a ComfyUI node graph dict."""
    for node in obj.values():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        if cls in _COMFYUI_LATENT_CLASSES:
            inputs = node.get("inputs", {})
            w = inputs.get("width")
            h = inputs.get("height")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                return int(w), int(h)
    return None, None


def extract_resolution(raw_prompt: str | None, raw_meta_json: str | None) -> tuple[int | None, int | None]:
    """Extract resolution from parameter text or metadata JSON."""
    if raw_prompt:
        m = _RE_SIZE.search(raw_prompt)
        if m:
            return int(m.group(1)), int(m.group(2))

    if raw_meta_json:
        try:
            outer = json.loads(raw_meta_json)
            comment_str = outer.get("Comment") if isinstance(outer, dict) else None
            if comment_str:
                data = json.loads(comment_str)
                w = data.get("width")
                h = data.get("height")
                if w and h:
                    return int(w), int(h)
            if isinstance(outer, dict):
                w = outer.get("width")
                h = outer.get("height")
                if w and h:
                    return int(w), int(h)
                # BUG-40: ComfyUI node graph
                cw, ch = _extract_comfyui_resolution(outer)
                if cw and ch:
                    return cw, ch
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return None, None
