"""ComfyUI JSON extraction helpers."""

import json

# Keys that may contain ComfyUI JSON but also other formats' data.
# For these keys, require explicit ComfyUI pattern match (numeric keys,
# class_type, or nodes) to avoid false positives with NAI/A1111 data.
_AMBIGUOUS_KEYS = frozenset(("exif:UserComment",))


def _is_comfyui_dict(obj: dict) -> bool:
    """Check if a parsed JSON dict matches ComfyUI prompt/workflow patterns."""
    if any(k.isdigit() for k in list(obj.keys())[:5]):
        return True
    if "nodes" in obj:
        return True
    return any(isinstance(v, dict) and "class_type" in v for v in list(obj.values())[:10])


def extract_comfyui_json(chunks: dict[str, str]) -> tuple[str | None, dict | None]:
    for key in ("prompt", "workflow", "exif:UserComment"):
        raw = chunks.get(key)
        if not raw or not raw.strip():
            continue
        raw = raw.strip()

        if not (raw.startswith("{") or raw.startswith("[")):
            continue

        strict = key in _AMBIGUOUS_KEYS

        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and _is_comfyui_dict(obj):
                return raw, obj
            # Ambiguous keys: only accept confirmed ComfyUI patterns
            if strict:
                continue
            return raw, obj
        except (json.JSONDecodeError, TypeError):
            if strict:
                continue
            return raw, None

    return None, None
