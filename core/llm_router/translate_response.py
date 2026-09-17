"""OpenAI response to Anthropic response translation."""

from __future__ import annotations

import json
import secrets

from .errors import TranslationError

_FINISH_REASON_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "end_turn",
}


def openai_response_to_anthropic(openai_resp: dict, requested_model: str) -> dict:
    choices = openai_resp.get("choices") or []
    if not choices:
        raise TranslationError("openai response has no choices")
    choice = choices[0]
    msg = choice.get("message", {})

    content_blocks: list[dict] = []
    text = msg.get("content")
    if text:
        content_blocks.append({"type": "text", "text": text})

    for tc in msg.get("tool_calls") or []:
        try:
            fn = tc["function"]
            arguments = fn.get("arguments", "{}")
            try:
                parsed_input = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                parsed_input = {"_raw": arguments}
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id") or f"toolu_{secrets.token_hex(8)}",
                "name": fn["name"],
                "input": parsed_input,
            })
        except (KeyError, TypeError) as exc:
            raise TranslationError(f"malformed tool_call: {exc}") from exc

    finish = choice.get("finish_reason", "stop")
    usage = openai_resp.get("usage") or {}
    return {
        "id": openai_resp.get("id") or f"msg_{secrets.token_hex(12)}",
        "type": "message",
        "role": "assistant",
        "model": requested_model,
        "content": content_blocks,
        "stop_reason": _FINISH_REASON_MAP.get(finish, "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }
