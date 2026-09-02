"""Prompt/parameter extraction helpers for NovelAI v4 metadata."""



def extract_base_and_char_prompts(data: dict, key: str, fallback_key: str) -> tuple[list[str], list[dict[str, str]]]:
    parts: list[str] = []
    chars: list[dict[str, str]] = []

    if key in data:
        payload = data[key]
        caption = payload.get("caption", {}) if isinstance(payload, dict) else {}
        base = caption.get("base_caption", "") if isinstance(caption, dict) else ""
        if base:
            parts.append(base)

        for i, char in enumerate(caption.get("char_captions", []) if isinstance(caption, dict) else []):
            char_text = char.get("char_caption", "") if isinstance(char, dict) else ""
            if not char_text:
                continue
            # Character prompts are added to chars only, not mixed into parts (main prompt)
            label = char_text.split(",")[0].strip() if char_text else f"Character {i + 1}"
            chars.append({"label": label, "prompt": char_text})

    if not parts and fallback_key in data and data[fallback_key]:
        parts.append(str(data[fallback_key]))

    return parts, chars


def extract_params(data: dict) -> dict[str, str]:
    params: dict[str, str] = {}
    for key in ("steps", "scale", "seed", "sampler", "noise_schedule", "sm", "sm_dyn", "cfg_rescale", "width", "height"):
        if key in data:
            params[key] = str(data[key])
    if "request_type" in data:
        params["request_type"] = data["request_type"]
    return params
