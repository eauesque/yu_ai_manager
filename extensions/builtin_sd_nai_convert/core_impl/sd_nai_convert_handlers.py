"""Request handlers for SD<->NAI conversion APIs."""

from typing import Any

from .sd_nai_convert_engine import convert_nai_to_sd, convert_sd_to_nai

_MAX_PROMPT_CHARS = 8192  # per-prompt character limit (matches wildcard line limit)


def _validate_prompt_pair(data: dict[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    prompt = data.get("prompt") or ""
    negative = data.get("negative") or ""
    if not isinstance(prompt, str):
        return "", "", {}, {"error": "prompt must be a string", "code": "invalid_prompt"}
    if not isinstance(negative, str):
        return "", "", {}, {"error": "negative must be a string", "code": "invalid_negative"}
    options = data.get("options")
    if not isinstance(options, dict):
        options = {}
    if len(prompt) > _MAX_PROMPT_CHARS or len(negative) > _MAX_PROMPT_CHARS:
        return "", "", {}, {
            "error": f"Prompt too long (max {_MAX_PROMPT_CHARS} chars)",
            "code": "prompt_too_long",
        }
    return prompt, negative, options, None


def handle_sd_to_nai(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Convert prompt/negative from SD format to NAI format."""
    prompt, negative, options, err = _validate_prompt_pair(data)
    if err:
        return err, 400

    strip_lora = options.get("strip_lora", True)
    strip_embedding = options.get("strip_embedding", True)
    emphasis = options.get("convert_emphasis", True)

    return {
        "prompt": convert_sd_to_nai(
            prompt,
            strip_lora=strip_lora,
            strip_embedding=strip_embedding,
            convert_emphasis=emphasis,
        ),
        "negative": convert_sd_to_nai(
            negative,
            strip_lora=strip_lora,
            strip_embedding=strip_embedding,
            convert_emphasis=emphasis,
        ),
        "direction": "sd_to_nai",
        "options": {
            "strip_lora": strip_lora,
            "strip_embedding": strip_embedding,
            "convert_emphasis": emphasis,
        },
    }, 200


def handle_nai_to_sd(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Convert prompt/negative from NAI format to SD format."""
    prompt, negative, options, err = _validate_prompt_pair(data)
    if err:
        return err, 400
    emphasis = options.get("convert_emphasis", True)

    return {
        "prompt": convert_nai_to_sd(prompt, convert_emphasis=emphasis),
        "negative": convert_nai_to_sd(negative, convert_emphasis=emphasis),
        "direction": "nai_to_sd",
        "options": {"convert_emphasis": emphasis},
    }, 200


def handle_batch_convert(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Batch-convert prompts and return payload with HTTP status."""
    items = data.get("items", [])
    direction = data.get("direction", "sd_to_nai")
    options = data.get("options")
    if not isinstance(options, dict):
        options = {}

    if not items:
        return {"error": "No items provided"}, 400
    if len(items) > 100:
        return {"error": "Max 100 items per batch"}, 400
    if direction not in ("sd_to_nai", "nai_to_sd"):
        return {"error": "Invalid direction: must be 'sd_to_nai' or 'nai_to_sd'"}, 400

    results = []
    for item in items:
        prompt = item.get("prompt", "") if isinstance(item, dict) else str(item)
        if len(prompt) > _MAX_PROMPT_CHARS:
            return {"error": f"Item prompt too long (max {_MAX_PROMPT_CHARS} chars)"}, 400
        if direction == "sd_to_nai":
            converted = convert_sd_to_nai(
                prompt,
                strip_lora=options.get("strip_lora", True),
                strip_embedding=options.get("strip_embedding", True),
                convert_emphasis=options.get("convert_emphasis", True),
            )
        else:
            converted = convert_nai_to_sd(
                prompt,
                convert_emphasis=options.get("convert_emphasis", True),
            )
        results.append({"original": prompt, "converted": converted})

    return {"results": results, "direction": direction, "count": len(results)}, 200
